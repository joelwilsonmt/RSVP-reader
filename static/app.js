"use strict";

// ── state ────────────────────────────────────────────────────────────────────
const state = {
  words: [],
  idx: 0,
  total: 0,
  relpath: "",
  title: "",
  playing: false,
  wpm: 350,
  timer: null,
  browsePath: "",
  saveTimer: null,
};

// ── helpers ──────────────────────────────────────────────────────────────────
function $(id) { return document.getElementById(id); }

function showView(name) {
  document.querySelectorAll(".view").forEach(v => v.classList.remove("active"));
  $("view-" + name).classList.add("active");
}

function fmtSize(bytes) {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(0) + " KB";
  return (bytes / 1024 / 1024).toFixed(1) + " MB";
}

function fmtRelTime(isoStr) {
  const d = new Date(isoStr.endsWith("Z") ? isoStr : isoStr + "Z");
  const diff = Date.now() - d.getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 2) return "just now";
  if (mins < 60) return mins + "m ago";
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return hrs + "h ago";
  return Math.floor(hrs / 24) + "d ago";
}

// Theme persisted in localStorage
function getTheme() { return localStorage.getItem("rsvp-theme") || "dark"; }
function setTheme(t) {
  document.documentElement.setAttribute("data-theme", t);
  localStorage.setItem("rsvp-theme", t);
}
function toggleTheme() { setTheme(getTheme() === "dark" ? "light" : "dark"); }

// ── ORP calculation ───────────────────────────────────────────────────────────
function orp(word) {
  // Strip leading/trailing punctuation for length calc, but display full word
  const bare = word.replace(/^[^a-zA-Z0-9À-ɏ]+/, "")
                   .replace(/[^a-zA-Z0-9À-ɏ]+$/, "");
  const len = bare.length || word.length;
  let idx;
  if (len <= 1)       idx = 0;
  else if (len <= 5)  idx = 1;
  else if (len <= 9)  idx = 2;
  else if (len <= 13) idx = 3;
  else                idx = 4;

  // Map ORP index back to position in full word
  // Find first alpha-num char in word, offset by idx
  let start = 0;
  for (let i = 0; i < word.length; i++) {
    if (/[a-zA-Z0-9À-ɏ]/.test(word[i])) { start = i; break; }
  }
  const orpPos = Math.min(start + idx, word.length - 1);
  return {
    left:  word.slice(0, orpPos),
    pivot: word[orpPos],
    right: word.slice(orpPos + 1),
  };
}

// ── pacing ────────────────────────────────────────────────────────────────────
function wordDelay(word, baseMs) {
  if (word === "¶") return baseMs * 2.0; // paragraph pause (word hidden)
  const bare = word.replace(/^[^a-zA-Z0-9À-ɏ]+/, "")
                   .replace(/[^a-zA-Z0-9À-ɏ]+$/, "");
  let m = 1.0;
  if (/[,;:\-)]$/.test(word)) m *= 1.5;
  if (/[.!?]$/.test(word))    m *= 2.2;
  if (bare.length > 8)        m *= 1.3;
  return baseMs * m;
}

// ── word display ──────────────────────────────────────────────────────────────
function renderWord(word) {
  if (word === "¶") {
    $("orp-left").textContent  = "";
    $("orp-char").textContent  = "";
    $("orp-right").textContent = "";
    return;
  }
  const { left, pivot, right } = orp(word);
  $("orp-left").textContent  = left;
  $("orp-char").textContent  = pivot;
  $("orp-right").textContent = right;
}

function updateCounter() {
  $("player-counter").textContent =
    `${state.idx + 1} / ${state.total}`;
  $("progress-slider").value = state.idx;
}

// ── playback ──────────────────────────────────────────────────────────────────
function baseMs() { return 60000 / state.wpm; }

function scheduleNext() {
  if (!state.playing || state.idx >= state.total) return;
  const word = state.words[state.idx];
  renderWord(word);
  updateCounter();
  const delay = wordDelay(word, baseMs());
  state.timer = setTimeout(() => {
    state.idx++;
    if (state.idx >= state.total) {
      pause();
    } else {
      scheduleNext();
    }
  }, delay);
}

function play() {
  if (state.idx >= state.total) return;
  state.playing = true;
  $("btn-play").textContent = "⏸";
  $("view-player").classList.remove("is-paused");
  scheduleNext();
  startSaveTimer();
}

function pause() {
  state.playing = false;
  clearTimeout(state.timer);
  $("btn-play").textContent = "▶";
  $("view-player").classList.add("is-paused");
  stopSaveTimer();
  saveProgress();
  renderContextPanel();
}

function togglePlay() {
  if (state.playing) pause(); else play();
}

function seekTo(idx) {
  state.idx = Math.max(0, Math.min(state.total - 1, idx));
  renderWord(state.words[state.idx]);
  updateCounter();
  $("progress-slider").value = state.idx;
}

function seek(delta) {
  seekTo(state.idx + delta);
  if (state.playing) return; // panel updates handled in pause
  renderContextPanel();
}

function restart() {
  const wasPlaying = state.playing;
  pause();
  state.idx = 0;
  renderWord(state.words[0] || "");
  updateCounter();
  if (wasPlaying) play();
}

// ── context panel ─────────────────────────────────────────────────────────────

function renderContextPanel() {
  const panel = $("context-panel");

  // Render a window of words around current position
  const BEFORE = 200;
  const AFTER  = 600;
  const start = Math.max(0, state.idx - BEFORE);
  const end   = Math.min(state.total, state.idx + AFTER);

  const inner = document.createElement("div");
  inner.className = "context-panel-inner";

  let para = document.createElement("p");
  para.className = "ctx-para";
  let prevWasBreak = true;

  for (let i = start; i < end; i++) {
    const word = state.words[i];

    if (word === "¶") {
      if (para.hasChildNodes()) {
        inner.appendChild(para);
        para = document.createElement("p");
        para.className = "ctx-para";
      }
      prevWasBreak = true;
      continue;
    }

    if (!prevWasBreak) {
      para.appendChild(document.createTextNode(" "));
    }
    prevWasBreak = false;

    const span = document.createElement("span");
    span.className = "ctx-word" + (i === state.idx ? " ctx-current" : "");
    span.textContent = word;
    span.dataset.idx = i;
    span.addEventListener("click", () => {
      seekTo(Number(span.dataset.idx));
      // Re-highlight without full re-render
      panel.querySelectorAll(".ctx-current").forEach(el => el.classList.remove("ctx-current"));
      span.classList.add("ctx-current");
    });
    para.appendChild(span);
  }
  if (para.hasChildNodes()) inner.appendChild(para);

  panel.innerHTML = "";
  panel.appendChild(inner);

  // Scroll current word into view within the panel
  requestAnimationFrame(() => {
    const cur = inner.querySelector(".ctx-current");
    if (cur) cur.scrollIntoView({ block: "center", behavior: "smooth" });
  });
}

// ── progress saving ───────────────────────────────────────────────────────────
function saveProgress() {
  if (!state.relpath) return;
  fetch("/api/progress", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      relpath: state.relpath,
      title: state.title,
      word_index: state.idx,
      total_words: state.total,
    }),
  }).catch(() => {});
}

function saveProgressBeacon() {
  if (!state.relpath) return;
  navigator.sendBeacon("/api/progress", JSON.stringify({
    relpath: state.relpath,
    title: state.title,
    word_index: state.idx,
    total_words: state.total,
  }));
}

function startSaveTimer() {
  stopSaveTimer();
  state.saveTimer = setInterval(saveProgress, 5000);
}
function stopSaveTimer() {
  clearInterval(state.saveTimer);
  state.saveTimer = null;
}

// ── open a file ───────────────────────────────────────────────────────────────
async function openFile(relpath, title) {
  pause();
  showView("loading");
  $("loading-msg").textContent = `Opening "${title}"…`;

  try {
    const res = await fetch(`/api/file/words?relpath=${encodeURIComponent(relpath)}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    state.words   = data.words;
    state.total   = data.total;
    state.relpath = data.relpath;
    state.title   = data.title;
    state.idx     = data.start;

    $("player-title").textContent = data.title;
    $("progress-slider").max   = Math.max(0, data.total - 1);
    $("progress-slider").value = data.start;

    renderWord(state.words[state.idx] || "");
    updateCounter();
    showView("player");
    $("view-player").classList.add("is-paused");
    renderContextPanel();
  } catch (err) {
    alert("Failed to load file: " + err.message);
    showView("home");
  }
}

// ── browse ────────────────────────────────────────────────────────────────────
const EXT_ICON = {
  ".epub": "📖",
  ".pdf":  "📄",
  ".txt":  "📝",
  ".md":   "📝",
};

async function browse(path) {
  state.browsePath = path;
  const res = await fetch(`/api/browse?path=${encodeURIComponent(path)}`);
  if (!res.ok) { console.error("Browse error", res.status); return; }
  const data = await res.json();

  if (data.error) {
    const list = $("file-list");
    list.innerHTML = "";
    const msg = document.createElement("div");
    msg.style.cssText = "color:var(--text-dim);padding:0.75rem 0;";
    msg.innerHTML = `<span style="color:var(--accent)">⚠</span> ${data.error} — click the folder pill above to choose one.`;
    list.appendChild(msg);
    return;
  }

  // Breadcrumb
  const bc = $("breadcrumb");
  bc.innerHTML = "";
  const rootSeg = document.createElement("span");
  rootSeg.className = "breadcrumb-seg";
  rootSeg.textContent = "Library";
  rootSeg.addEventListener("click", () => browse(""));
  bc.appendChild(rootSeg);

  if (data.path) {
    const parts = data.path.split("/").filter(Boolean);
    parts.forEach((part, i) => {
      const sep = document.createElement("span");
      sep.className = "breadcrumb-sep";
      sep.textContent = " / ";
      bc.appendChild(sep);

      const seg = document.createElement("span");
      const segPath = parts.slice(0, i + 1).join("/");
      if (i === parts.length - 1) {
        seg.className = "breadcrumb-current";
        seg.textContent = part;
      } else {
        seg.className = "breadcrumb-seg";
        seg.textContent = part;
        seg.addEventListener("click", () => browse(segPath));
      }
      bc.appendChild(seg);
    });
  }

  // File list
  const list = $("file-list");
  list.innerHTML = "";
  if (!data.entries.length) {
    list.innerHTML = '<p style="color:var(--text-dim);padding:0.5rem 0">Empty folder</p>';
    return;
  }

  data.entries.forEach(entry => {

    const row = document.createElement("div");
    row.className = "file-row" + (entry.type === "file" && !entry.supported ? " unsupported" : "");

    const icon = document.createElement("span");
    icon.className = "file-icon";
    icon.textContent = entry.type === "dir" ? "📁" : (EXT_ICON[entry.ext] || "📄");
    row.appendChild(icon);

    const name = document.createElement("span");
    name.className = "file-name";
    name.textContent = entry.name;
    row.appendChild(name);

    if (entry.type === "file" && entry.ext) {
      const ext = document.createElement("span");
      ext.className = "file-ext";
      ext.textContent = entry.ext.replace(".", "");
      row.appendChild(ext);
    }

    if (entry.type === "file" && entry.size != null) {
      const sz = document.createElement("span");
      sz.className = "file-size";
      sz.textContent = fmtSize(entry.size);
      row.appendChild(sz);
    }

    if (entry.type === "dir") {
      row.addEventListener("click", () => browse(entry.relpath));
    } else if (entry.supported) {
      row.addEventListener("click", () => openFile(entry.relpath, entry.name.replace(/\.[^.]+$/, "")));
    }

    list.appendChild(row);
  });
}

// ── continue reading ──────────────────────────────────────────────────────────
async function loadContinue() {
  const res = await fetch("/api/progress");
  if (!res.ok) return;
  const items = await res.json();
  const section = $("continue-section");
  const list = $("continue-list");
  list.innerHTML = "";

  if (!items.length) { section.style.display = "none"; return; }
  section.style.display = "";

  items.forEach(item => {
    const card = document.createElement("div");
    card.className = "continue-card";

    const info = document.createElement("div");
    info.className = "continue-info";

    const title = document.createElement("div");
    title.className = "continue-title";
    title.textContent = item.title;

    const meta = document.createElement("div");
    meta.className = "continue-meta";
    meta.textContent = `${item.percent}%  ·  ${fmtRelTime(item.updated_at)}`;

    const barWrap = document.createElement("div");
    barWrap.className = "continue-bar-wrap";
    const bar = document.createElement("div");
    bar.className = "continue-bar";
    bar.style.width = item.percent + "%";
    barWrap.appendChild(bar);

    info.appendChild(title);
    info.appendChild(meta);
    info.appendChild(barWrap);

    const dismiss = document.createElement("button");
    dismiss.className = "continue-dismiss";
    dismiss.textContent = "✕";
    dismiss.title = "Dismiss";
    dismiss.addEventListener("click", async (e) => {
      e.stopPropagation();
      await fetch(`/api/progress?relpath=${encodeURIComponent(item.relpath)}`, { method: "DELETE" });
      loadContinue();
    });

    card.appendChild(info);
    card.appendChild(dismiss);
    card.addEventListener("click", () => openFile(item.relpath, item.title));
    list.appendChild(card);
  });
}

// ── keyboard ──────────────────────────────────────────────────────────────────
document.addEventListener("keydown", (e) => {
  if (!$("view-player").classList.contains("active")) return;
  if (e.target.tagName === "INPUT") return;

  switch (true) {
    case e.code === "Space":
      e.preventDefault();
      togglePlay();
      break;
    case e.code === "ArrowLeft" && e.shiftKey:
      e.preventDefault();
      seek(-50);
      break;
    case e.code === "ArrowRight" && e.shiftKey:
      e.preventDefault();
      seek(50);
      break;
    case e.code === "ArrowLeft":
      e.preventDefault();
      seek(-10);
      break;
    case e.code === "ArrowRight":
      e.preventDefault();
      seek(10);
      break;
  }
});

// ── WPM controls ─────────────────────────────────────────────────────────────
function setWpm(v) {
  v = Math.max(100, Math.min(1000, v));
  state.wpm = v;
  $("wpm-input").value  = v;
  $("wpm-slider").value = v;
}

$("wpm-slider").addEventListener("input", () => setWpm(Number($("wpm-slider").value)));
$("wpm-input").addEventListener("change", () => setWpm(Number($("wpm-input").value)));

// ── progress slider ───────────────────────────────────────────────────────────
$("progress-slider").addEventListener("input", () => {
  const wasPlaying = state.playing;
  if (wasPlaying) pause();
  state.idx = Number($("progress-slider").value);
  renderWord(state.words[state.idx] || "");
  updateCounter();
  if (wasPlaying) play();
});

// ── button wiring ──────────────────────────────────────────────────────────────
$("btn-play").addEventListener("click", togglePlay);
$("btn-skip-back-10").addEventListener("click", () => seek(-10));
$("btn-skip-fwd-10").addEventListener("click",  () => seek(10));
$("btn-skip-back-50").addEventListener("click", () => seek(-50));
$("btn-skip-fwd-50").addEventListener("click",  () => seek(50));
$("btn-restart").addEventListener("click", restart);

$("btn-back").addEventListener("click", () => {
  pause();
  showView("home");
  loadContinue();
  browse(state.browsePath || "");
});

$("theme-toggle-home").addEventListener("click", toggleTheme);
$("theme-toggle-player").addEventListener("click", toggleTheme);

// ── unload save ───────────────────────────────────────────────────────────────
document.addEventListener("visibilitychange", () => {
  if (document.hidden) saveProgressBeacon();
});
window.addEventListener("beforeunload", saveProgressBeacon);

// ── folder config ─────────────────────────────────────────────────────────────
async function loadConfig() {
  const res = await fetch("/api/config");
  if (!res.ok) return;
  const { books_dir } = await res.json();
  $("folder-path").textContent = books_dir;
}

// ── filesystem picker ─────────────────────────────────────────────────────────
const picker = {
  mode: "folder",   // "folder" | "file"
  cwd: "/",
  selected: null,   // { path, type }
};

async function pickerNavigate(absPath) {
  let res = await fetch(`/api/fs?path=${encodeURIComponent(absPath)}`);
  // If path doesn't exist, fall back up the tree until something works
  if (!res.ok) {
    const parts = absPath.split("/").filter(Boolean);
    while (parts.length > 0 && !res.ok) {
      parts.pop();
      const fallback = "/" + parts.join("/") || "/";
      res = await fetch(`/api/fs?path=${encodeURIComponent(fallback)}`);
    }
    if (!res.ok) return;
  }
  const data = await res.json();

  picker.cwd = data.path;
  picker.selected = null;
  $("picker-cwd").textContent = data.path;
  $("picker-selection").textContent = "";
  $("picker-select").disabled = true;

  const list = $("picker-list");
  list.innerHTML = "";

  // ".." row
  if (data.parent) {
    const up = document.createElement("div");
    up.className = "picker-row picker-row--up";
    up.innerHTML = `<span class="file-icon">↑</span><span class="picker-name">.. (up)</span>`;
    up.addEventListener("click", () => pickerNavigate(data.parent));
    list.appendChild(up);
  }

  if (!data.entries.length) {
    const empty = document.createElement("div");
    empty.style.cssText = "padding:1rem;color:var(--text-dim);font-size:0.85rem;";
    empty.textContent = "Empty or inaccessible folder.";
    list.appendChild(empty);
  }

  data.entries.forEach(entry => {
    const isDir = entry.type === "dir";
    const selectable = isDir
      ? picker.mode === "folder"
      : picker.mode === "file" && entry.supported;

    const row = document.createElement("div");
    row.className = "picker-row" + (!selectable && !isDir ? " unsupported" : "");

    const icon = document.createElement("span");
    icon.className = "file-icon";
    icon.textContent = isDir ? "📁" : (EXT_ICON[entry.ext] || "📄");

    const name = document.createElement("span");
    name.className = "picker-name";
    name.textContent = entry.name;

    row.appendChild(icon);
    row.appendChild(name);

    if (!isDir && entry.ext) {
      const ext = document.createElement("span");
      ext.className = "picker-ext";
      ext.textContent = entry.ext.replace(".", "");
      row.appendChild(ext);
    }

    row.addEventListener("click", () => {
      if (isDir) {
        if (picker.mode === "folder") {
          // single-click selects; double-click navigates
          if (picker.selected?.path === entry.path) {
            pickerNavigate(entry.path);
          } else {
            list.querySelectorAll(".picker-row").forEach(r => r.classList.remove("selected"));
            row.classList.add("selected");
            picker.selected = entry;
            $("picker-selection").textContent = entry.path;
            $("picker-select").disabled = false;
          }
        } else {
          pickerNavigate(entry.path);
        }
      } else if (selectable) {
        list.querySelectorAll(".picker-row").forEach(r => r.classList.remove("selected"));
        row.classList.add("selected");
        picker.selected = entry;
        $("picker-selection").textContent = entry.path;
        $("picker-select").disabled = false;
      }
    });

    // double-click a dir always navigates
    if (isDir) {
      row.addEventListener("dblclick", () => pickerNavigate(entry.path));
    }

    list.appendChild(row);
  });
}

async function openPicker(mode, startPath) {
  picker.mode = mode;
  picker.selected = null;
  $("picker-title").textContent = mode === "folder" ? "Choose Folder" : "Choose File";
  $("picker-select").disabled = true;
  $("picker-selection").textContent = "";
  $("picker-overlay").style.display = "flex";
  await pickerNavigate(startPath || picker.cwd || "/");
}

function closePicker() {
  $("picker-overlay").style.display = "none";
}

async function pickerConfirm() {
  if (!picker.selected) return;
  if (picker.mode === "folder") {
    const res = await fetch("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ books_dir: picker.selected.path }),
    });
    const data = await res.json();
    if (!res.ok) { alert(data.error || "Invalid folder"); return; }
    $("folder-path").textContent = data.books_dir;
    state.browsePath = "";
    closePicker();
    browse("");
  } else {
    // file mode: derive title from filename, open directly
    const relpath = picker.selected.path;
    const title = relpath.split("/").pop().replace(/\.[^.]+$/, "");
    closePicker();
    // Temporarily expand BOOKS_DIR to parent so safe_resolve passes
    // (file picker opens files by absolute path — set books_dir to its parent)
    const parent = relpath.split("/").slice(0, -1).join("/") || "/";
    await fetch("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ books_dir: parent }),
    });
    const filename = relpath.split("/").pop();
    $("folder-path").textContent = parent;
    state.browsePath = "";
    openFile(filename, title);
  }
}

$("picker-close").addEventListener("click", closePicker);
$("picker-cancel").addEventListener("click", closePicker);
$("picker-select").addEventListener("click", pickerConfirm);
$("picker-overlay").addEventListener("click", (e) => {
  if (e.target === $("picker-overlay")) closePicker();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && $("picker-overlay").style.display !== "none") closePicker();
});

$("folder-display").addEventListener("click", () => {
  const cur = $("folder-path").textContent || "/";
  openPicker("folder", cur);
});

$("btn-choose-file").addEventListener("click", () => {
  const cur = $("folder-path").textContent || "/";
  openPicker("file", cur);
});

// ── init ──────────────────────────────────────────────────────────────────────
setTheme(getTheme());
setWpm(350);
loadConfig();
loadContinue();
browse("");
showView("home");
