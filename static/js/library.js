// Library surfaces: the Now feed, the Files browser, and the filesystem picker.

import { api } from "./api.js";
import { $, h, icon, fmtDuration, fmtClock, fmtSize, stem, toneFor, typoCover } from "./util.js";
import { AVG_MULT } from "./rsvp.js";
import { settings } from "./settings.js";
import { openSheet, closeSheet, toast, toastError } from "./ui.js";

let progressCache = null;  // null until the first successful load
export const progressByPath = () => new Map((progressCache || []).map((p) => [p.path, p]));
const smooth = () => matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth";

const readHref = (path, extra = {}) => "#/read?" + new URLSearchParams({ p: path, ...extra });

function coverEl(item, { thumb = false } = {}) {
  const title = item.title || "Untitled";
  if (item.has_cover && item.book_id) {
    const img = h("img", { src: api.coverUrl(item.book_id), alt: "", loading: thumb ? "lazy" : "eager", decoding: "async" });
    img.addEventListener("error", () => img.replaceWith(typoCover(title, item.author)), { once: true });
    return img;
  }
  return typoCover(title, item.author);
}

// ── NOW feed ────────────────────────────────────────────────────────────────

let feedObserver;
let feedGen = 0;

// The slide in view, so a re-render (refocus, remove) keeps the reader's place.
function currentSlide(feed) {
  const n = Math.round(feed.scrollTop / Math.max(1, feed.clientHeight));
  return { n, id: feed.children[n]?.dataset.id };
}

export async function renderFeed() {
  const feed = $("feed");
  const gen = ++feedGen;
  const was = feed.children.length ? currentSlide(feed) : null;
  let items;
  try {
    items = await api.progress();
  } catch (err) {
    if (gen !== feedGen) return;
    toastError(err);
    if (!progressCache) {
      feed.textContent = "";
      feed.append(noteSlide("Can't load your books", err.message,
        [h("button", { class: "btn btn--solid", type: "button", onclick: () => renderFeed() }, h("span", {}, "Try again"))]));
      return;
    }
    items = progressCache;
  }
  if (gen !== feedGen) return;
  progressCache = items;
  feed.textContent = "";
  feedObserver?.disconnect();

  if (!items.length) {
    feed.append(noteSlide("Nothing on the go",
      "Pick a book from your library folder. Your place is saved on the server, so you can pick up on any device.",
      [h("a", { class: "btn btn--solid", href: "#/files" }, icon("files"), h("span", {}, "Browse files"))]));
    $("feed-count").textContent = "";
    return;
  }

  items.forEach((item, n) => feed.append(bookSlide(item, n, items.length)));
  feed.append(noteSlide("Up next?", "Find the next book in your library folder.",
    [h("a", { class: "btn btn--media", href: "#/files" }, icon("files"), h("span", {}, "Browse files"))]));

  feedObserver = new IntersectionObserver((entries) => {
    for (const e of entries) {
      if (e.isIntersecting && e.intersectionRatio > 0.6) {
        const n = e.target.dataset.n;
        $("feed-count").textContent = n ? `${+n + 1} / ${items.length}` : "";
      }
    }
  }, { root: feed, threshold: [0.6] });
  feed.querySelectorAll(".slide").forEach((s) => feedObserver.observe(s));

  if (was) {
    const same = was.id ? [...feed.children].findIndex((s) => s.dataset.id === was.id) : -1;
    const n = same >= 0 ? same : Math.min(was.n, feed.children.length - 1);
    feed.scrollTop = n * feed.clientHeight;
  }
}

function bookSlide(item, n) {
  const remainingWords = Math.max(0, item.total_words - item.word_index);
  const left = (remainingWords * AVG_MULT * 60000) / settings.wpm;
  const tone = toneFor(item.book_id);
  const field = h("div", { class: "slide-field", style: `--tone:${tone}` });
  if (item.has_cover) field.style.backgroundImage = `url("${api.coverUrl(item.book_id)}")`;

  const resume = h("a", { class: "rail-labeled", href: readHref(item.path), "aria-label": `Resume ${item.title}` },
    h("span", { class: "rail-btn rail-btn--primary" }, icon("play", "icon icon--fill")), h("span", {}, "Resume"));
  const chapters = h("a", { class: "rail-btn", href: readHref(item.path, { ch: 1 }), "aria-label": `Chapters of ${item.title}` },
    icon("chapters"), h("span", { class: "rail-count" }, "Chapters"));
  const remove = h("button", { class: "rail-btn", type: "button", "aria-label": `Remove ${item.title} from Now` },
    icon("x"), h("span", { class: "rail-count" }, "Remove"));
  remove.addEventListener("click", () => removeItem(item));

  return h("article", { class: "slide", dataset: { n, id: item.book_id }, style: `--tone:${tone}`, "aria-label": item.title },
    field,
    h("div", { class: "slide-cover", style: `--tone:${tone}` }, coverEl(item)),
    h("div", { class: "slide-info" },
      h("h2", { class: "slide-title" }, item.title),
      item.author ? h("p", { class: "slide-author" }, item.author) : null,
      h("p", { class: "slide-caption" },
        `${Math.floor(item.percent)}% · ~${fmtDuration(left)} left`,
        // A finish time is only useful when it falls within one sitting.
        left < 6 * 3600000 ? h("span", { class: "dim" }, ` · done by ${fmtClock(new Date(Date.now() + left))}`) : null),
      h("div", { class: "slide-progress", role: "progressbar", "aria-valuenow": Math.floor(item.percent), "aria-valuemin": 0, "aria-valuemax": 100, "aria-label": "Progress" },
        h("span", { style: `width:${item.percent}%` })),
    ),
    h("div", { class: "rail" }, chapters, remove, resume),
  );
}

function noteSlide(title, body, actions) {
  return h("article", { class: "slide slide--note" },
    h("div", { class: "slide-field" }),
    h("div", {},
      h("h2", { class: "slide-note-title" }, title),
      h("p", { class: "slide-note-body" }, body),
      h("div", { class: "slide-note-actions" }, actions)));
}

async function removeItem(item) {
  try {
    await api.deleteProgress(item.book_id);
  } catch (err) { toastError(err); return; }
  renderFeed();
  toast(`Removed "${item.title}" from Now.`, {
    action: "Undo",
    onAction: async () => {
      await api.saveProgress({ book_id: item.book_id, path: item.path, title: item.title, author: item.author,
        word_index: item.word_index, total_words: item.total_words, seconds_read: 0 }).catch(toastError);
      renderFeed();
    },
  });
}

export function feedKey(e) {
  const feed = $("feed");
  const step = feed.clientHeight;
  if (e.key === "ArrowDown" || e.key === "j") { feed.scrollBy({ top: step, behavior: smooth() }); return true; }
  if (e.key === "ArrowUp" || e.key === "k") { feed.scrollBy({ top: -step, behavior: smooth() }); return true; }
  // Enter/Space resume the book in view, but only when nothing else has focus.
  const free = e.target === document.body || e.target === feed || e.target === document.documentElement;
  if (free && (e.key === "Enter" || e.key === " ")) {
    const n = Math.round(feed.scrollTop / step);
    const link = feed.children[n]?.querySelector(".rail-labeled, .btn");
    if (link) { link.click(); return true; }
  }
  return false;
}

// ── FILES ───────────────────────────────────────────────────────────────────

let filesPath = "";
let filesGen = 0;
let metaObserver;
const metaQueue = [];
let metaActive = 0;

export async function renderFiles(path) {
  if (path !== undefined) filesPath = path;
  const gen = ++filesGen;
  const list = $("file-list");
  list.textContent = "";
  for (let i = 0; i < 6; i++) list.append(h("li", { class: "skeleton", "aria-hidden": "true" }));

  let data;
  try {
    [data] = await Promise.all([api.browse(filesPath), api.progress().then((p) => { progressCache = p; }).catch(() => {})]);
  } catch (err) {
    if (gen !== filesGen) return;
    list.textContent = "";
    list.append(h("li", { class: "file-empty" }, h("strong", {}, "Can't open this folder."), err.message));
    return;
  }
  if (gen !== filesGen) return;  // a later folder was opened while this one loaded
  filesPath = data.path;
  renderCrumbs(data);
  list.textContent = "";

  if (data.error) {
    list.append(h("li", { class: "file-empty" },
      h("strong", {}, "Library folder not found."),
      `${data.error}. Choose another with Library folder above.`));
    return;
  }
  if (!data.entries.length) {
    list.append(h("li", { class: "file-empty" }, h("strong", {}, "This folder is empty."),
      "Drop EPUB, MOBI, AZW3, PDF, TXT or Markdown files into it and they'll show up here."));
    return;
  }

  metaObserver?.disconnect();
  metaObserver = new IntersectionObserver((entries) => {
    for (const e of entries) if (e.isIntersecting) { metaObserver.unobserve(e.target); queueMeta(e.target); }
  }, { rootMargin: "200px" });

  const prog = progressByPath();
  for (const entry of data.entries) list.append(h("li", {}, fileRow(entry, prog.get(entry.path))));
}

function renderCrumbs(data) {
  const nav = $("crumbs");
  nav.textContent = "";
  const root = data.root.replace(/\/+$/, "") || "/";
  const rel = data.path.startsWith(root) ? data.path.slice(root.length).split("/").filter(Boolean) : [];
  const rootName = root.split("/").filter(Boolean).pop() || "/";
  const segs = [{ name: rootName, path: root }];
  rel.forEach((name, i) => segs.push({ name, path: root + "/" + rel.slice(0, i + 1).join("/") }));
  segs.forEach((s, i) => {
    if (i) nav.append(h("span", { class: "sep", "aria-hidden": "true" }, "/"));
    if (i === segs.length - 1) nav.append(h("span", { "aria-current": "location" }, s.name));
    else nav.append(h("button", { type: "button", onclick: () => goFiles(s.path) }, s.name));
  });
}

export function goFiles(path) {
  location.hash = "#/files?" + new URLSearchParams({ path });
}

function fileRow(entry, prog) {
  if (entry.type === "dir") {
    return h("button", { class: "file-row", type: "button", onclick: () => goFiles(entry.path) },
      h("span", { class: "file-thumb file-thumb--dir" }, icon("folder")),
      h("span", { class: "file-main" }, h("span", { class: "file-name" }, entry.name)),
      h("span", { class: "file-end" }, icon("chev")));
  }
  const ext = entry.ext.replace(".", "").toUpperCase();
  if (!entry.supported) {
    return h("button", { class: "file-row", type: "button", disabled: true },
      h("span", { class: "file-thumb" }, icon("file")),
      h("span", { class: "file-main" },
        h("span", { class: "file-name" }, entry.name),
        h("span", { class: "file-sub" }, `${ext || "File"} · not supported`)),
      h("span", { class: "file-end" }));
  }
  const thumb = h("span", { class: "file-thumb" }, typoCover(stem(entry.name), ""));
  const name = h("span", { class: "file-name" }, stem(entry.name));
  const sub = h("span", { class: "file-sub" });
  const fill = (author) => {
    sub.textContent = "";
    if (prog) sub.append(h("span", { class: "pct" }, `${Math.floor(prog.percent)}%`), " · ");
    sub.append([author, ext, entry.size != null ? fmtSize(entry.size) : null].filter(Boolean).join(" · "));
  };
  fill(prog?.author);
  const row = h("a", { class: "file-row", href: readHref(entry.path) },
    thumb, h("span", { class: "file-main" }, name, sub), h("span", { class: "file-end" }));
  row._meta = { entry, thumb, name, fill };
  metaObserver.observe(row);
  return row;
}

function queueMeta(row) { metaQueue.push(row); pumpMeta(); }

function pumpMeta() {
  while (metaActive < 4 && metaQueue.length) {
    const row = metaQueue.shift();
    if (!row.isConnected) continue;
    metaActive++;
    const { entry, thumb, name, fill } = row._meta;
    api.meta(entry.path).then((m) => {
      if (m.title) name.textContent = m.title;
      fill(m.author);
      thumb.textContent = "";
      thumb.append(coverEl({ ...m, title: m.title || stem(entry.name) }, { thumb: true }));
    }).catch(() => {}).finally(() => { metaActive--; pumpMeta(); });
  }
}

// ── filesystem picker (library folder, or a one-off file) ───────────────────

const picker = { mode: "folder", cwd: "/", gen: 0 };

async function pickerGo(path, gen = ++picker.gen) {
  let data;
  try { data = await api.fs(path); }
  catch (err) {
    if (gen !== picker.gen) return;
    if (err.status === 404 && path !== "/") return pickerGo(path.split("/").slice(0, -1).join("/") || "/", gen);
    toastError(err);
    return;
  }
  if (gen !== picker.gen) return;  // "Use this folder" must commit the folder on screen
  picker.cwd = data.path;
  $("picker-cwd").textContent = data.path;
  $("picker-selection").textContent = picker.mode === "folder" ? data.path : "Tap a book to open it";
  $("picker-confirm").disabled = picker.mode !== "folder";
  $("picker-confirm").hidden = picker.mode !== "folder";
  const list = $("picker-list");
  list.textContent = "";
  if (data.parent) {
    list.append(h("li", {}, h("button", { class: "file-row", type: "button", onclick: () => pickerGo(data.parent) },
      h("span", { class: "file-thumb" }, icon("back")),
      h("span", { class: "file-main" }, h("span", { class: "file-name" }, "Up one level")),
      h("span", {}))));
  }
  for (const e of data.entries) {
    const isDir = e.type === "dir";
    if (!isDir && picker.mode === "folder") continue;
    const ok = isDir || e.supported;
    list.append(h("li", {}, h("button", {
      class: "file-row", type: "button", disabled: !ok,
      onclick: () => isDir ? pickerGo(e.path) : pickFile(e.path),
    },
      h("span", { class: "file-thumb" }, icon(isDir ? "folder" : "file")),
      h("span", { class: "file-main" }, h("span", { class: "file-name" }, e.name)),
      h("span", { class: "file-end" }, isDir ? icon("chev") : (e.ext || "").replace(".", "")))));
  }
  if (!list.children.length) list.append(h("li", { class: "file-empty" }, "Nothing to show here."));
}

function pickFile(path) {
  closeSheet("sheet-picker");
  location.hash = readHref(path);
}

export async function openPicker(mode) {
  picker.mode = mode;
  $("picker-title").textContent = mode === "folder" ? "Library folder" : "Open a file";
  openSheet("sheet-picker");
  let start = picker.cwd;
  try { start = (await api.config()).books_dir; } catch {}
  pickerGo(start);
}

export function initLibrary() {
  $("btn-open-elsewhere").addEventListener("click", () => openPicker("file"));
  $("btn-change-root").addEventListener("click", () => openPicker("folder"));
  $("picker-confirm").addEventListener("click", async () => {
    try {
      const { books_dir } = await api.setLibrary(picker.cwd);
      closeSheet("sheet-picker");
      toast(`Library folder set to ${books_dir}`);
      goFiles(books_dir);
    } catch (err) { toastError(err); }
  });
}
