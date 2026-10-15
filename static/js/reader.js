// The reader: playback engine, chrome, context text, chapters, gestures.

import { api } from "./api.js";
import { $, h, fmtDuration, fmtClock, setRangeFill } from "./util.js";
import { BREAK, orp, multiplier, buildTimeline, spanMs, sentenceStart, sentenceEnd,
         nextSentence, prevSentence, chapterAt } from "./rsvp.js";
import { openSheet, closeSheet, toast, toastError, anySheetOpen } from "./ui.js";
import { settings, saveSettings } from "./settings.js";

const RAMP_WORDS = 10;
const RESUME_REWIND = 5;
const WIDE = window.matchMedia("(min-width: 960px)");

const r = {
  book: null,          // { book_id, path, title, author, words, chapters, total }
  cum: null,           // timeline prefix sums
  idx: 0,
  playing: false,
  timer: 0,
  nextAt: 0,
  ramp: 0,
  pausedAt: 0,
  playTick: 0,         // performance.now() of last seconds accounting
  secondsPending: 0,
  wordsPending: 0,     // words actually shown by playback since the last save
  saveTimer: 0,
  seekSaveTimer: 0,    // pending save after a paused seek
  seeked: false,       // the reader picked this word; the next play must not rewind
  metaTimer: 0,
  wakeLock: null,
  contextOpen: false,
  loadToken: 0,
};

const view = () => $("view-reader");

// ── loading ─────────────────────────────────────────────────────────────────

export async function openBook(path, { chapters = false } = {}) {
  const token = ++r.loadToken;
  if (r.book && r.book.path === path) {
    refreshAll();
    if (WIDE.matches) openContext();
    syncFromServer();
    if (chapters) openChapters();
    return;
  }
  pause();
  flushSave();
  r.book = null;
  view().classList.remove("is-playing");
  $("reader-title").textContent = path.split("/").pop().replace(/\.[^.]+$/, "");
  $("reader-meta").textContent = "";
  $("reader-chapter").textContent = "";
  $("reader-sentence").textContent = "";
  setWord("");
  setStatus("Preparing text. Large books can take a few seconds.", true);
  closeContext();

  let data;
  try {
    data = await api.book(path);
  } catch (err) {
    if (token !== r.loadToken) return;
    setStatus(err.status === 404 ? "This file is no longer there." : err.message);
    return;
  }
  if (token !== r.loadToken) return;

  r.book = data;
  r.cum = buildTimeline(data.words);
  r.idx = Math.max(0, Math.min(data.start || 0, data.total - 1));
  r.pausedAt = 0;
  r.seeked = false;
  setStatus("");

  const scrub = $("scrub");
  scrub.max = Math.max(0, data.total - 1);
  renderTicks();
  $("reader-title").textContent = data.title;
  $("rail-ch-count").textContent = data.chapters.length > 1 ? data.chapters.length : "";
  $("rail-chapters").hidden = data.chapters.length < 2;
  refreshAll();
  if (WIDE.matches) openContext();
  if (chapters) openChapters();
}

// Another device may have moved on since this book was loaded.
async function syncFromServer() {
  const b = r.book;
  if (!b || r.playing) return;
  try {
    const row = (await api.progress()).find((p) => p.book_id === b.book_id);
    if (row && row.word_index !== r.idx && r.book === b && !r.playing) {
      seekTo(row.word_index, { user: false });
      toast("Picked up where you left off on another device.", { ms: 2500 });
    }
  } catch {}
}

export function leaveReader() {
  pause();
  flushSave();
  closeContext();
  r.loadToken++;
}

export function currentBook() { return r.book; }

// ── playback ────────────────────────────────────────────────────────────────

const beat = () => 60000 / settings.wpm;

function step() {
  const b = r.book;
  if (!r.playing || !b) return;
  if (r.idx >= b.total) { finish(); return; }
  const word = b.words[r.idx];
  setWord(word);
  updateScrub();
  let delay = multiplier(word) * beat();
  if (r.ramp > 0) { delay *= 1 + 0.8 * (r.ramp / RAMP_WORDS); r.ramp--; }
  r.nextAt += delay;
  r.timer = setTimeout(() => {
    r.idx++;
    r.wordsPending++;
    if (r.idx >= b.total) { r.idx = b.total - 1; finish(); return; }
    step();
  }, Math.max(0, r.nextAt - performance.now()));
}

export function play() {
  const b = r.book;
  if (!b || r.playing) return;
  if (r.idx >= b.total - 1) r.idx = 0;
  if (settings.ramp) {
    const long = !r.pausedAt || Date.now() - r.pausedAt > 2000;
    if (long && !r.seeked) {
      // Re-establish context, but never back across a chapter start.
      const c = chapterAt(b.chapters, r.idx);
      const floor = c >= 0 ? b.chapters[c].index : 0;
      r.idx = Math.max(floor, r.idx - RESUME_REWIND);
    }
    r.ramp = RAMP_WORDS;
  }
  r.seeked = false;
  r.playing = true;
  r.nextAt = performance.now();
  r.playTick = performance.now();
  view().classList.add("is-playing");
  $("rail-play").setAttribute("aria-label", "Pause");
  $("rail-play-icon").setAttribute("href", "#i-pause");
  if (r.contextOpen) closeContext();
  acquireWakeLock();
  clearInterval(r.saveTimer);
  r.saveTimer = setInterval(() => save(), 8000);
  clearInterval(r.metaTimer);
  r.metaTimer = setInterval(updateMeta, 1000);
  step();
}

export function pause() {
  if (!r.playing) return;
  accountSeconds();
  r.playing = false;
  clearTimeout(r.timer);
  clearInterval(r.saveTimer);
  clearInterval(r.metaTimer);
  r.pausedAt = Date.now();
  view().classList.remove("is-playing", "show-chrome");
  $("rail-play").setAttribute("aria-label", "Play");
  $("rail-play-icon").setAttribute("href", "#i-play");
  releaseWakeLock();
  refreshAll();
  save();
  if (WIDE.matches) openContext();
}

export function toggle() { r.playing ? pause() : play(); }

function finish() {
  pause();
  toast("Finished. Nice.");
}

// user: the reader chose this word, so the next play starts exactly here (no rewind).
// A position synced from another device is not a user seek: resuming it still rewinds.
export function seekTo(i, { keepPlaying = true, user = true } = {}) {
  const b = r.book;
  if (!b) return;
  const was = r.playing;
  if (was) { clearTimeout(r.timer); }
  r.idx = Math.max(0, Math.min(b.total - 1, i));
  if (!was) r.seeked = user;
  if (was && keepPlaying) {
    r.nextAt = performance.now();
    step();
  } else {
    setWord(b.words[r.idx]);
    refreshAll();
    if (user) scheduleSave();  // playing saves on its own timer and on pause
  }
}

const seek = (d) => r.book && seekTo(r.idx + d);
const seekSentence = (dir) => r.book &&
  seekTo(dir > 0 ? nextSentence(r.book.words, r.idx) : prevSentence(r.book.words, r.idx));

function seekChapter(dir) {
  const b = r.book;
  if (!b || !b.chapters.length) return;
  const c = chapterAt(b.chapters, r.idx);
  let target;
  if (dir > 0) target = b.chapters[c + 1]?.index;
  else {
    const start = c >= 0 ? b.chapters[c].index : 0;
    target = r.idx - start > 20 || c <= 0 ? start : b.chapters[c - 1].index;
  }
  if (target != null) seekTo(target);
}

export function setWpm(v) {
  const wpm = Math.max(100, Math.min(800, Math.round(v / 5) * 5));
  if (wpm === settings.wpm) return;
  settings.wpm = wpm;
  saveSettings({ wpm });
  syncWpmUi();
  updateMeta();
}

// ── persistence ─────────────────────────────────────────────────────────────

function accountSeconds() {
  if (!r.playing || !r.playTick) return;
  const now = performance.now();
  r.secondsPending += (now - r.playTick) / 1000;
  r.playTick = now;
}

// Drains pending seconds/words into a payload; restore() puts them back if it never lands.
// Words travel only with at least a second, since the server caps words by seconds.
function payload() {
  const b = r.book;
  accountSeconds();
  const secs = Math.round(r.secondsPending);
  const words = secs > 0 ? r.wordsPending : 0;
  r.secondsPending -= secs;
  r.wordsPending -= words;
  const body = {
    book_id: b.book_id, path: b.path, title: b.title, author: b.author || null,
    word_index: r.idx, total_words: b.total, seconds_read: secs, words_read: words,
  };
  const restore = () => { r.secondsPending += secs; r.wordsPending += words; };
  return [body, restore];
}

export function save() {
  clearTimeout(r.seekSaveTimer);
  r.seekSaveTimer = 0;
  if (!r.book) return;
  const book = r.book;
  const [body, restore] = payload();
  api.saveProgress(body).catch(() => { if (r.book === book) restore(); });
}

function scheduleSave() {
  clearTimeout(r.seekSaveTimer);
  r.seekSaveTimer = setTimeout(save, 800);
}

// Leaving the book (or switching to another): don't drop a pending paused-seek save.
function flushSave() {
  if (r.seekSaveTimer) save();
}

export function saveBeacon() {
  if (!r.book) return;
  clearTimeout(r.seekSaveTimer);
  r.seekSaveTimer = 0;
  const [body, restore] = payload();
  if (!api.beacon(body)) restore();
}

// ── wake lock ───────────────────────────────────────────────────────────────

async function acquireWakeLock() {
  if (!("wakeLock" in navigator) || r.wakeLock || r.wakeLockPending) return;
  r.wakeLockPending = true;
  try {
    const lock = await navigator.wakeLock.request("screen");
    if (!r.playing) { lock.release().catch(() => {}); return; }  // paused while we waited
    r.wakeLock = lock;
    lock.addEventListener("release", () => { if (r.wakeLock === lock) r.wakeLock = null; });
  } catch {} finally {
    r.wakeLockPending = false;
  }
}
function releaseWakeLock() { r.wakeLock?.release().catch(() => {}); r.wakeLock = null; }

export function onVisibility(hidden) {
  if (hidden) { if (r.playing) pause(); saveBeacon(); }
  else syncFromServer();
}

// ── rendering ───────────────────────────────────────────────────────────────

const wl = $("w-left"), wp = $("w-pivot"), wr = $("w-right"), wordEl = $("word");

function setWord(word) {
  if (word === BREAK) {
    wl.textContent = ""; wp.textContent = "·"; wr.textContent = "";
    wordEl.classList.add("is-break");
    setFit(1);
    return;
  }
  wordEl.classList.remove("is-break");
  const { left, pivot, right } = orp(word || "");
  wl.textContent = left; wp.textContent = pivot; wr.textContent = right;
  setFit(fitFor(left, pivot, right));
}

// Each side of the pivot gets half the line and clips what overflows, so a word too
// long for its half is shrunk (pivot stays put) instead of losing its end.
const measureCtx = document.createElement("canvas").getContext("2d");
let fitBase = null;  // { font, half } at full size; reset when the layout or fonts change
let fit = 1;

function fitFor(left, pivot, right) {
  if (!fitBase) {
    const cs = getComputedStyle(wordEl);
    const px = parseFloat(cs.fontSize) / fit;
    fitBase = { font: `${cs.fontWeight} ${px}px ${cs.fontFamily}`, half: wordEl.clientWidth / 2 };
  }
  if (!fitBase.half) return 1;
  measureCtx.font = fitBase.font;
  const m = (t) => measureCtx.measureText(t).width;
  const p = m(pivot) / 2;
  const need = (Math.max(m(left), m(right)) + p) / (fitBase.half - 2);
  return need > 1 ? Math.max(0.4, 1 / need) : 1;
}

function setFit(f) {
  if (f === fit) return;
  fit = f;
  wordEl.style.setProperty("--fit", f.toFixed(3));
}

function refit() {
  fitBase = null;
  if (r.book) setWord(r.book.words[r.idx]);
}
new ResizeObserver(refit).observe(wordEl);  // window resize, rotation, side panel opening
document.fonts?.addEventListener("loadingdone", refit);

function setStatus(msg, loading = false) {
  const s = $("stage-status");
  s.hidden = !msg;
  s.textContent = msg;
  s.classList.toggle("is-loading", loading);
}

function updateScrub() {
  const s = $("scrub");
  s.value = r.idx;
  setRangeFill(s);
}

function updateMeta() {
  const b = r.book;
  if (!b) return;
  const left = spanMs(r.cum, r.idx, b.total, settings.wpm);
  const pct = b.total > 1 ? Math.floor((r.idx / (b.total - 1)) * 100) : 0;
  const done = new Date(Date.now() + left);
  $("reader-meta").textContent = `${pct}% · ${fmtDuration(left)} left · done ${fmtClock(done)}`;
  const c = chapterAt(b.chapters, r.idx);
  $("reader-chapter").textContent = c >= 0 ? b.chapters[c].title : "";
}

function updateSentence() {
  const b = r.book;
  const btn = $("reader-sentence");
  if (!b || r.playing) { btn.textContent = ""; return; }
  const s = sentenceStart(b.words, r.idx), e = sentenceEnd(b.words, r.idx, 45);
  btn.textContent = "";
  for (let i = s; i <= e; i++) {
    const w = b.words[i];
    if (w === BREAK) continue;
    if (i > s) btn.append(" ");
    btn.append(i === r.idx ? h("mark", {}, w) : w);
  }
}

function refreshAll() {
  if (!r.book) return;
  setWord(r.book.words[r.idx]);
  updateScrub();
  updateMeta();
  updateSentence();
  if (r.contextOpen) renderContext();
}

function renderTicks() {
  const box = $("scrub-ticks");
  box.textContent = "";
  const b = r.book;
  if (!b || b.chapters.length < 2 || b.chapters.length > 120) return;
  for (const c of b.chapters) {
    if (c.index <= 0) continue;
    box.append(h("i", { style: `left:${(c.index / (b.total - 1)) * 100}%` }));
  }
}

export function syncWpmUi() {
  $("rail-wpm-count").textContent = settings.wpm;
  $("wpm-value").textContent = settings.wpm;
  const sl = $("wpm-slider");
  sl.value = settings.wpm;
  setRangeFill(sl);
  if (r.book) {
    const left = spanMs(r.cum, r.idx, r.book.total, settings.wpm);
    $("wpm-preview").textContent = `${fmtDuration(left)} left in this book · done ${fmtClock(new Date(Date.now() + left))}`;
  } else $("wpm-preview").textContent = "";
}

export function syncGuides() {
  view().classList.toggle("no-guides", !settings.pivot_guides);
}

// ── context text ────────────────────────────────────────────────────────────

const CTX_BEFORE = 250, CTX_AFTER = 700;

function renderContext() {
  const b = r.book;
  const body = $("context-body");
  if (!b) { body.textContent = ""; return; }
  const start = Math.max(0, r.idx - CTX_BEFORE);
  const end = Math.min(b.total, r.idx + CTX_AFTER);
  const frag = document.createDocumentFragment();
  const chapStarts = new Map(b.chapters.map((c) => [c.index, c.title]));

  if (start > 0) frag.append(h("button", { class: "btn btn--quiet ctx-more", type: "button", "data-jump": start - 1 }, "Earlier text"));

  let p = h("p", { class: "ctx-p" });
  let fresh = true;
  for (let i = start; i < end; i++) {
    if (chapStarts.has(i)) {
      if (p.childNodes.length) { frag.append(p); p = h("p", { class: "ctx-p" }); }
      frag.append(h("h3", { class: "ctx-chapter" }, chapStarts.get(i)));
      fresh = true;
    }
    const w = b.words[i];
    if (w === BREAK) {
      if (p.childNodes.length) { frag.append(p); p = h("p", { class: "ctx-p" }); }
      fresh = true;
      continue;
    }
    if (!fresh) p.append(" ");
    fresh = false;
    const span = h("span", { class: i === r.idx ? "ctx-w is-current" : "ctx-w", "data-i": i }, w);
    p.append(span);
  }
  if (p.childNodes.length) frag.append(p);
  if (end < b.total) frag.append(h("button", { class: "btn btn--quiet ctx-more", type: "button", "data-jump": end }, "Later text"));

  body.textContent = "";
  body.append(frag);
  requestAnimationFrame(() => body.querySelector(".is-current")?.scrollIntoView({ block: "center" }));
}

function markCurrent() {
  const body = $("context-body");
  body.querySelector(".is-current")?.classList.remove("is-current");
  body.querySelector(`[data-i="${r.idx}"]`)?.classList.add("is-current");
}

export function openContext() {
  if (!r.book) return;
  const c = $("context");
  r.contextOpen = true;
  view().classList.add("ctx-open");
  $("rail-text").setAttribute("aria-pressed", "true");
  if (c.hidden) {
    c.hidden = false;
    c.classList.add("is-entering");
    requestAnimationFrame(() => requestAnimationFrame(() => c.classList.remove("is-entering")));
  }
  renderContext();
}

export function closeContext() {
  r.contextOpen = false;
  view().classList.remove("ctx-open");
  $("rail-text").setAttribute("aria-pressed", "false");
  $("context").hidden = true;
}

function toggleContext() { r.contextOpen ? closeContext() : (pause(), openContext()); }

// ── chapters sheet ──────────────────────────────────────────────────────────

function openChapters() {
  const b = r.book;
  if (!b || b.chapters.length < 2) return;
  pause();
  const list = $("chapter-list");
  list.textContent = "";
  const cur = chapterAt(b.chapters, r.idx);
  b.chapters.forEach((c, n) => {
    const end = b.chapters[n + 1]?.index ?? b.total;
    const isDone = n < cur, isCur = n === cur;
    let time;
    if (isDone) time = "Read";
    else if (isCur) time = fmtDuration(spanMs(r.cum, r.idx, end, settings.wpm)) + " left";
    else time = fmtDuration(spanMs(r.cum, c.index, end, settings.wpm));
    const row = h("button", {
      class: "chapter-row" + (isDone ? " is-done" : "") + (isCur ? " is-current" : ""),
      type: "button", "aria-current": isCur ? "true" : null,
      onclick: () => { seekTo(c.index); closeSheet("sheet-chapters"); },
    },
      h("span", { class: "chapter-num" }, String(n + 1).padStart(2, "0")),
      h("span", { class: "chapter-name" }, c.title || `Chapter ${n + 1}`),
      h("span", { class: "chapter-time" }, time),
      isCur ? h("span", { class: "chapter-bar" }, h("span", { style: `width:${((r.idx - c.index) / Math.max(1, end - c.index)) * 100}%` })) : null,
    );
    list.append(h("li", {}, row));
  });
  openSheet("sheet-chapters");
  requestAnimationFrame(() => list.querySelector(".is-current")?.scrollIntoView({ block: "center" }));
}

// ── keyboard & gestures ─────────────────────────────────────────────────────

export function onKey(e) {
  if (e.metaKey || e.ctrlKey || e.altKey) return false;
  const k = e.key;
  if (k === " " || k === "k") { toggle(); return true; }
  if (k === "ArrowLeft") { e.shiftKey ? seekSentence(-1) : seek(-10); return true; }
  if (k === "ArrowRight") { e.shiftKey ? seekSentence(1) : seek(10); return true; }
  if (k === "ArrowUp") { setWpm(settings.wpm + 25); toast(`${settings.wpm} wpm`, { ms: 900 }); return true; }
  if (k === "ArrowDown") { setWpm(settings.wpm - 25); toast(`${settings.wpm} wpm`, { ms: 900 }); return true; }
  if (k === "[") { seekChapter(-1); return true; }
  if (k === "]") { seekChapter(1); return true; }
  if (k === "t" || k === "T") { toggleContext(); return true; }
  if (k === "c" || k === "C") { openChapters(); return true; }
  return false;
}

function initGestures() {
  const stage = $("stage");
  let sx = 0, sy = 0, active = false;
  stage.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    active = true; sx = e.clientX; sy = e.clientY;
  });
  stage.addEventListener("pointercancel", () => { active = false; });
  stage.addEventListener("pointerup", (e) => {
    if (!active) return;
    active = false;
    const dx = e.clientX - sx, dy = e.clientY - sy;
    if (Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy) * 1.3) { seekSentence(dx < 0 ? 1 : -1); return; }
    if (dy < -60 && Math.abs(dy) > Math.abs(dx)) { pause(); openContext(); return; }
    if (Math.abs(dx) < 12 && Math.abs(dy) < 12) toggle();
  });

  // Desktop: moving the mouse while playing reveals the chrome briefly.
  let hideT;
  view().addEventListener("pointermove", (e) => {
    if (e.pointerType !== "mouse" || !r.playing) return;
    view().classList.add("show-chrome");
    clearTimeout(hideT);
    hideT = setTimeout(() => view().classList.remove("show-chrome"), 1600);
  });
}

// ── wiring ──────────────────────────────────────────────────────────────────

export function initReader({ onBack }) {
  initGestures();
  $("rail-play").addEventListener("click", toggle);
  $("rail-text").addEventListener("click", toggleContext);
  $("rail-chapters").addEventListener("click", openChapters);
  $("rail-wpm").addEventListener("click", () => { syncWpmUi(); openSheet("sheet-wpm"); });
  $("reader-sentence").addEventListener("click", () => { pause(); openContext(); });
  $("btn-context-close").addEventListener("click", closeContext);
  $("btn-reader-back").addEventListener("click", onBack);
  $("btn-reader-settings").addEventListener("click", () => { pause(); openSheet("sheet-settings"); });

  $("context-body").addEventListener("click", (e) => {
    const w = e.target.closest("[data-i]");
    if (w) { seekTo(+w.dataset.i); markCurrent(); updateSentence(); return; }
    const j = e.target.closest("[data-jump]");
    if (j) { seekTo(+j.dataset.jump); renderContext(); }
  });

  const scrub = $("scrub");
  let wasPlaying = false;
  scrub.addEventListener("pointerdown", () => { wasPlaying = r.playing; if (wasPlaying) pause(); });
  scrub.addEventListener("input", () => {
    r.idx = +scrub.value;
    if (!r.playing) r.seeked = true;
    setRangeFill(scrub);
    if (r.book) { setWord(r.book.words[r.idx]); updateMeta(); }
  });
  scrub.addEventListener("change", () => {
    refreshAll();
    save();
    if (wasPlaying) { wasPlaying = false; play(); }
  });

  const slider = $("wpm-slider");
  slider.addEventListener("input", () => setWpm(+slider.value));
  $("wpm-down").addEventListener("click", () => setWpm(settings.wpm - 25));
  $("wpm-up").addEventListener("click", () => setWpm(settings.wpm + 25));

  $("btn-restart").addEventListener("click", () => {
    if (!r.book) return;
    const prev = r.idx;
    seekTo(0);
    save();
    closeSheet("sheet-settings");
    toast("Back to the beginning.", { action: "Undo", onAction: () => { seekTo(prev); save(); } });
  });

  WIDE.addEventListener("change", () => {
    if (!view().classList.contains("is-active")) return;
    if (WIDE.matches && !r.playing) openContext();
  });
}

