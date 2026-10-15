// DOM and formatting helpers.

export const $ = (id) => document.getElementById(id);

export function h(tag, props = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "dataset") Object.assign(el.dataset, v);
    else if (k === "style") el.style.cssText = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "html") el.innerHTML = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) {
    if (c == null || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

const SVG_NS = "http://www.w3.org/2000/svg";
export function icon(name, cls = "icon") {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("class", cls);
  svg.setAttribute("aria-hidden", "true");
  const use = document.createElementNS(SVG_NS, "use");
  use.setAttribute("href", "#i-" + name);
  svg.append(use);
  return svg;
}

export function fmtDuration(ms) {
  const mins = Math.max(0, Math.round(ms / 60000));
  if (mins < 1) return "<1m";
  if (mins < 60) return mins + "m";
  const h = Math.floor(mins / 60), m = mins % 60;
  return m ? `${h}h ${m}m` : `${h}h`;
}

export function fmtClock(date) {
  return date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

export function fmtNum(n) { return Math.round(n).toLocaleString(); }

export function fmtCompact(n) {
  if (n >= 10000) return (n / 1000).toFixed(n >= 100000 ? 0 : 1).replace(/\.0$/, "") + "k";
  return fmtNum(n);
}

export function fmtSize(bytes) {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return Math.round(bytes / 1024) + " KB";
  return (bytes / 1024 / 1024).toFixed(1) + " MB";
}

export function fmtAgo(iso) {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 2) return "just now";
  if (mins < 60) return mins + "m ago";
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return hrs + "h ago";
  const days = Math.floor(hrs / 24);
  return days === 1 ? "yesterday" : days + "d ago";
}

export function stem(name) { return name.replace(/\.[^.]+$/, ""); }

export function debounce(fn, ms) {
  let t;
  return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}

// Muted tones from the world palette; a book keeps its tone by id.
const TONES = ["#1e2533", "#2b2724", "#1f2a26", "#2a2130", "#262a33", "#30281f", "#1c2a2e"];
export function toneFor(id = "") {
  let n = 0;
  for (let i = 0; i < id.length; i++) n = (n * 31 + id.charCodeAt(i)) >>> 0;
  return TONES[n % TONES.length];
}

export function typoCover(title, author) {
  const len = title.length;
  const size = len < 14 ? 2.6 : len < 28 ? 2.1 : len < 48 ? 1.7 : 1.35;
  return h("div", { class: "typo-cover", style: `--tc-size:${size}rem` },
    h("div", { class: "typo-cover-title" }, title),
    h("div", {}, h("div", { class: "typo-cover-rule" }), h("div", { class: "typo-cover-author" }, author || "")));
}

export function setRangeFill(input) {
  const min = +input.min || 0, max = +input.max || 100;
  const p = max > min ? ((+input.value - min) / (max - min)) * 100 : 0;
  input.style.setProperty("--p", p + "%");
}
