// Reading settings (server-side, shared across devices) and theme (per device).

import { api } from "./api.js";
import { debounce } from "./util.js";

export const settings = { wpm: 350, pivot_guides: true, ramp: true };

export async function loadSettings() {
  try { Object.assign(settings, await api.settings()); } catch {}
  return settings;
}

// Changes made within the debounce window merge into one request.
let pending = {};
const push = debounce(() => {
  const patch = pending;
  pending = {};
  api.saveSettings(patch).catch(() => {});
}, 500);
export function saveSettings(patch) {
  pending = { ...pending, ...patch };
  push();
}

// ── word size (per device: the right size depends on the screen) ────────────

export const WORD_SIZE = { min: 0.6, max: 1.2 };

export function getWordSize() {
  try {
    const s = +localStorage.getItem("rsvp-word-size");
    return s >= WORD_SIZE.min && s <= WORD_SIZE.max ? s : 1;
  } catch { return 1; }
}

export function applyWordSize(s) {
  s = Math.max(WORD_SIZE.min, Math.min(WORD_SIZE.max, Math.round(s * 20) / 20));
  document.documentElement.style.setProperty("--word-size", s);
  try { s === 1 ? localStorage.removeItem("rsvp-word-size") : localStorage.setItem("rsvp-word-size", String(s)); } catch {}
  return s;
}

// ── theme ───────────────────────────────────────────────────────────────────

export function getTheme() {
  try { return localStorage.getItem("rsvp-theme") || "auto"; } catch { return "auto"; }
}

export function applyTheme(t) {
  const root = document.documentElement;
  if (t === "light" || t === "dark") root.dataset.theme = t; else delete root.dataset.theme;
  try { t === "auto" ? localStorage.removeItem("rsvp-theme") : localStorage.setItem("rsvp-theme", t); } catch {}
  const light = t === "light" || (t === "auto" && matchMedia("(prefers-color-scheme: light)").matches);
  document.querySelector('meta[name="theme-color"]').content = light ? "#f3f1ee" : "#0a0a0a";
}
