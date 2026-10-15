---
version: 1
slug: "templates-index-html"
primary_target: "templates/index.html"
related_targets: ["static/app.js","static/style.css"]
---

# Surface: RSVP Reader app (library feed + reader)

Scope: the whole single-page app (templates/index.html, static/). Visitor mode: Operate.
Audience/job: owner reading his backlog fast, phone in bed at night, one hand; desktop secondary.
Constraints: vanilla JS/CSS, no build, light payload (only self-hosted fonts, no CDN at runtime). Dark is the use-scene default; light theme follows system or setting.

## Direction contract

THESIS: One thing owns the screen. The library is a vertical snap feed where each book fills the viewport; the reader is the word alone, full-bleed. Refuses the category default of a cover grid plus a reader with a bottom toolbar.

OWN-WORLD: Void #0A0A0A ground, ink #121316 / slate #1E2026 / mist #2A2F39 layers, fog #5A6472 secondary, sand #C7B9A6 warm neutral, white glyphs as the only interface colour, a single signal #FF4D6A reserved for the pivot letter and live state. Tall condensed display caps (Antonio) for titles and counts; system sans for UI; Atkinson Hyperlegible for the word. 1.5px outline icons that fill when engaged. Bottom scrim carries text over cover art.

STORY: Open the app and the book you're reading fills the screen, its cover as the field, title low-left, time left in the caption. Tap Resume in the rail and you're reading in one tap. Flick up for the next book in progress. Pause, and the caption expands into the surrounding text.

FIRST VIEWPORT: Feed. Full-bleed blurred cover field with bottom scrim. Lower-left: condensed title at about 3.5rem, author line, caption "42% · 2h 14m left · done by 23:41", hairline progress. Right rail, low (thumb zone): Resume (primary, filled), Chapters, Remove; counts under glyphs. Bottom nav bar: Now / Files / Stats. Reader: word centered on void, fixation ticks above and below the signal pivot; rail glyphs (WPM with live count, Chapters, Text, Settings) low-right; title and caption low-left; chrome fades to nothing while playing.

FORM: Full-bleed vertical feed (catalog: pop-culture-shelf-vertical-video-feed-surface), a dealt challenger chosen by the user over the assigned 5th grounded direction; seed key 36adef31. Signature interaction: the library as a snap feed (one book per screen, the next a flick away), with the reader caption that expands into the context text on pause. Motion grammar: hard snaps, 200ms ease-out fades, no motion during playback, reduced motion swaps slides for fades.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

## Decisions after review

- Nav label "Pace" instead of "Stats": the view reports pace (words, time, wpm), matching PRODUCT.md principle 2.
- Reader settings live in the low-right rail (thumb zone); the top bar holds only back and the running chapter head.
- Feed caption shows "done by HH:MM" only when the finish falls within 6h; beyond that, time left alone.
