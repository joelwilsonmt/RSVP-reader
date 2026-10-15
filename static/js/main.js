// App shell: routing, global keys, settings sheet.

import { $, setRangeFill } from "./util.js";
import { initSheets, openSheet, closeSheet, anySheetOpen } from "./ui.js";
import { settings, loadSettings, saveSettings, getTheme, applyTheme, getWordSize, applyWordSize } from "./settings.js";
import { renderFeed, renderFiles, feedKey, initLibrary } from "./library.js";
import { renderStats } from "./stats.js";
import * as reader from "./reader.js";

let route = "";
let enteredReaderFromApp = false;

function parseHash() {
  const raw = location.hash.replace(/^#\/?/, "");
  const [name, qs = ""] = raw.split("?");
  return { name: name || "now", params: new URLSearchParams(qs) };
}

function show(name) {
  document.querySelectorAll(".view").forEach((v) => v.classList.toggle("is-active", v.dataset.view === name));
  document.body.dataset.route = name;
  document.querySelectorAll(".tab").forEach((t) => {
    if (t.dataset.tab === name) t.setAttribute("aria-current", "page"); else t.removeAttribute("aria-current");
  });
}

function onRoute() {
  const { name, params } = parseHash();
  if (route === "reader" && name !== "reader") reader.leaveReader();
  if (anySheetOpen()) document.querySelectorAll("dialog[open]").forEach((d) => d.close());

  if (name === "read" && params.get("p")) {
    enteredReaderFromApp = route !== "" && route !== "reader";
    route = "reader";
    show("reader");
    reader.openBook(params.get("p"), { chapters: params.get("ch") === "1" });
    return;
  }
  if (name === "files") { route = "files"; show("files"); renderFiles(params.get("path") || ""); window.scrollTo(0, 0); return; }
  if (name === "stats") { route = "stats"; show("stats"); renderStats(); window.scrollTo(0, 0); return; }
  route = "now";
  show("now");
  renderFeed();
}

function backFromReader() {
  if (enteredReaderFromApp) history.back();
  else location.replace("#/now");
}

// ── keyboard ────────────────────────────────────────────────────────────────

document.addEventListener("keydown", (e) => {
  const tag = e.target.tagName;
  if (tag === "INPUT" && e.target.type !== "range" && e.target.type !== "checkbox") return;
  if (e.target.isContentEditable) return;

  if (e.key === "?") { openSheet("sheet-shortcuts"); e.preventDefault(); return; }
  if (anySheetOpen()) return;                       // <dialog> handles Esc itself

  if (route === "reader") {
    if (e.key === "Escape") {
      if (!$("context").hidden && !matchMedia("(min-width: 960px)").matches) reader.closeContext();
      else backFromReader();
      e.preventDefault();
      return;
    }
    if (tag === "INPUT" && (e.key === "ArrowLeft" || e.key === "ArrowRight")) return;  // scrubber
    if (reader.onKey(e)) e.preventDefault();
    return;
  }
  if (route === "now" && feedKey(e)) e.preventDefault();
});

// ── settings sheet ──────────────────────────────────────────────────────────

function syncSettingsUi() {
  const t = getTheme();
  document.querySelectorAll("[data-theme-choice]").forEach((b) =>
    b.setAttribute("aria-checked", String(b.dataset.themeChoice === t)));
  $("set-guides").checked = !!settings.pivot_guides;
  $("set-ramp").checked = !!settings.ramp;
  syncWordSizeUi(getWordSize());
  $("wakelock-note").hidden = "wakeLock" in navigator && window.isSecureContext;
}

function syncWordSizeUi(size) {
  const pct = Math.round(size * 100);
  $("set-size").value = pct;
  $("set-size-value").textContent = `${pct}%`;
  setRangeFill($("set-size"));
}

// Keep the word visible above the settings sheet so the size slider previews live.
function liftWord(open) {
  const view = $("view-reader");
  const sheet = $("sheet-settings");
  const on = open && route === "reader" && !matchMedia("(min-width: 960px)").matches;
  view.classList.toggle("sheet-lift", on);
  if (on) view.style.setProperty("--sheet-h", `${sheet.offsetHeight}px`);  // its height, not its (animating) position
}

function initSettingsSheet() {
  $("set-size").addEventListener("input", (e) => syncWordSizeUi(applyWordSize(+e.target.value / 100)));
  document.querySelectorAll("[data-theme-choice]").forEach((b) =>
    b.addEventListener("click", () => { applyTheme(b.dataset.themeChoice); syncSettingsUi(); }));
  $("set-guides").addEventListener("change", (e) => {
    settings.pivot_guides = e.target.checked; saveSettings({ pivot_guides: settings.pivot_guides }); reader.syncGuides();
  });
  $("set-ramp").addEventListener("change", (e) => {
    settings.ramp = e.target.checked; saveSettings({ ramp: settings.ramp });
  });
  $("sheet-settings").addEventListener("toggle", (e) => { syncSettingsUi(); liftWord(e.target.open); });
  $("btn-shortcuts").addEventListener("click", () => { closeSheet("sheet-settings"); openSheet("sheet-shortcuts"); });
}

// ── lifecycle ───────────────────────────────────────────────────────────────

document.addEventListener("visibilitychange", () => {
  if (route === "reader") reader.onVisibility(document.hidden);
  else if (!document.hidden && route === "now") renderFeed();
});
window.addEventListener("pagehide", () => { if (route === "reader") reader.saveBeacon(); });
window.addEventListener("hashchange", onRoute);

async function boot() {
  applyTheme(getTheme());
  initSheets();
  initLibrary();
  initSettingsSheet();
  reader.initReader({ onBack: backFromReader });
  await loadSettings();
  reader.syncGuides();
  reader.syncWpmUi();
  syncSettingsUi();
  onRoute();
}

boot();
