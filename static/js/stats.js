// Pace view: words and time this week, last 14 days, books in progress.

import { api } from "./api.js";
import { $, h, fmtDuration, fmtNum, fmtAgo } from "./util.js";

export async function renderStats() {
  const body = $("stats-body");
  let s, prog;
  try {
    [s, prog] = await Promise.all([api.stats(), api.progress()]);
  } catch (err) {
    body.textContent = "";
    body.append(h("p", { class: "stats-sub" }, err.message));
    return;
  }
  body.textContent = "";

  const week = s.week || { words: 0, seconds: 0 };
  const today = s.today || { words: 0, seconds: 0 };
  const activeDays = (s.days || []).slice(-7).filter((d) => d.words > 0).length;

  if (!week.words) {
    body.append(h("p", { class: "stats-lede" }, "No reading yet this week."),
      h("p", { class: "stats-sub" }, "Words and time show up here as you read. Nothing leaves your server."));
  } else {
    const wpm = week.seconds > 60 ? Math.round(week.words / (week.seconds / 60)) : null;
    body.append(
      h("p", { class: "stats-lede" },
        "This week ", h("b", {}, fmtNum(week.words)), " words in ", h("b", {}, fmtDuration(week.seconds * 1000)),
        wpm ? [" at ", h("b", {}, fmtNum(wpm)), " wpm"] : null, "."),
      h("p", { class: "stats-sub" },
        today.words ? `Today: ${fmtNum(today.words)} words in ${fmtDuration(today.seconds * 1000)}. ` : "Nothing read today yet. ",
        `Read on ${activeDays} of the last 7 days.`));
  }

  const days = s.days || [];
  if (days.length) {
    const max = Math.max(1, ...days.map((d) => d.words));
    const todayKey = days[days.length - 1].day;
    const bars = h("div", { class: "bars", role: "img", "aria-label": "Words read per day, last 14 days" });
    for (const d of days) {
      const date = new Date(d.day + "T12:00:00");
      bars.append(h("div", {
        class: "bar" + (d.words ? " is-active" : "") + (d.day === todayKey ? " is-today" : ""),
        title: `${date.toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" })}: ${fmtNum(d.words)} words`,
      },
        h("span", { class: "bar-fill", style: `height:${(d.words / max) * 100}%` }),
        h("span", { class: "bar-day" }, date.toLocaleDateString([], { weekday: "narrow" }))));
    }
    body.append(bars, h("p", { class: "bars-caption" }, h("span", {}, "Two weeks ago"), h("span", {}, `Peak ${fmtNum(max)} words`)));
  }

  if (prog.length) {
    const list = h("ul", { class: "file-list", role: "list" });
    for (const p of prog) {
      list.append(h("li", {}, h("a", { class: "file-row", href: "#/read?" + new URLSearchParams({ p: p.path }), style: "grid-template-columns:1fr auto" },
        h("span", { class: "file-main" },
          h("span", { class: "file-name" }, p.title),
          h("span", { class: "file-sub" }, h("span", { class: "pct" }, `${Math.floor(p.percent)}%`),
            ` · ${fmtNum(p.word_index)} of ${fmtNum(p.total_words)} words · ${fmtAgo(p.updated_at)}`)),
        h("span", { class: "file-end" }))));
    }
    body.append(h("section", { class: "stats-books" }, h("h2", { class: "stats-h" }, "In progress"), list));
  }
}
