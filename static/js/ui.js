// Sheets (native <dialog>) and toasts.

import { $, h } from "./util.js";

export function openSheet(id) {
  const d = $(id);
  if (!d.open) d.showModal();
  return d;
}

export function closeSheet(id) {
  const d = $(id);
  if (d.open) d.close();
}

export function anySheetOpen() {
  return !!document.querySelector("dialog[open]");
}

export function initSheets() {
  document.querySelectorAll("dialog.sheet").forEach((d) => {
    d.addEventListener("click", (e) => {
      if (e.target === d) {                          // backdrop, not the sheet's own padding
        const b = d.getBoundingClientRect();
        const inside = e.clientX >= b.left && e.clientX <= b.right && e.clientY >= b.top && e.clientY <= b.bottom;
        if (!inside) d.close();
      }
      if (e.target.closest("[data-close]")) d.close();
    });
  });
}

export function toast(message, { error = false, action, onAction, ms = 4000 } = {}) {
  const box = $("toasts");
  const el = h("div", { class: "toast" + (error ? " toast--error" : "") }, message);
  if (action) {
    const btn = h("button", { type: "button", style: "margin-left:14px;font-weight:700;text-decoration:underline;text-underline-offset:3px" }, action);
    btn.addEventListener("click", () => { onAction?.(); el.remove(); });
    el.append(btn);
  }
  box.append(el);
  setTimeout(() => el.remove(), action ? Math.max(ms, 6000) : ms);
}

export const toastError = (err) => toast(err.message || String(err), { error: true, ms: 6000 });
