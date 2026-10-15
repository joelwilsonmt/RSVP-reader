---
name: RSVP Reader
description: One word at a time, on the void, from your own shelf.
colors:
  void: "#0a0a0a"
  ink: "#121316"
  slate: "#1e2026"
  mist: "#2a2f39"
  fog: "#5a6472"
  sand: "#c7b9a6"
  white: "#f4f4f2"
  text-2: "#a3abb8"
  text-3: "#858e9c"
  signal: "#ff4d6a"
  guide: "#3a414d"
  on-media-2: "#c9ccd2"
  light-bg: "#f3f1ee"
  light-surface: "#ffffff"
  light-surface-2: "#e9e5df"
  light-line: "#d9d3ca"
  light-text-2: "#3d4450"
  light-signal: "#c81e45"
  light-guide: "#c7bfb3"
typography:
  display:
    fontFamily: "Antonio, Arial Narrow, sans-serif"
    fontSize: "clamp(3.25rem, 13.5vw, 5.5rem)"
    fontWeight: 600
    lineHeight: 0.9
    letterSpacing: "0.005em"
  headline:
    fontFamily: "Antonio, Arial Narrow, sans-serif"
    fontSize: "3rem"
    fontWeight: 600
    lineHeight: 0.9
    letterSpacing: "0.01em"
  title:
    fontFamily: "Antonio, Arial Narrow, sans-serif"
    fontSize: "1.75rem"
    fontWeight: 600
    lineHeight: 1
    letterSpacing: "0.01em"
  numeral:
    fontFamily: "Antonio, Arial Narrow, sans-serif"
    fontSize: "5rem"
    fontWeight: 600
    lineHeight: 0.9
    fontFeature: "tnum"
  word:
    fontFamily: "Atkinson Hyperlegible, system-ui, sans-serif"
    fontSize: "clamp(2.4rem, 10.5vw, 4.75rem)"
    fontWeight: 400
    lineHeight: 1.15
  reading:
    fontFamily: "Atkinson Hyperlegible, system-ui, sans-serif"
    fontSize: "1.0625rem"
    fontWeight: 400
    lineHeight: 1.65
  body:
    fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 600
    letterSpacing: "0.14em"
  glyph-count:
    fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "0.6875rem"
    fontWeight: 600
    letterSpacing: "0.04em"
    fontFeature: "tnum"
rounded:
  hairline: "3px"
  cover: "4px"
  focus: "6px"
  row: "10px"
  sheet: "16px"
  pill: "999px"
spacing:
  xs: "8px"
  sm: "14px"
  md: "20px"
  lg: "24px"
  xl: "32px"
  2xl: "48px"
components:
  button-solid:
    backgroundColor: "{colors.white}"
    textColor: "{colors.void}"
    typography: "{typography.label}"
    rounded: "{rounded.hairline}"
    padding: "0 18px"
    height: "44px"
  button-quiet:
    textColor: "{colors.text-2}"
    typography: "{typography.label}"
    rounded: "{rounded.hairline}"
    padding: "0 18px"
    height: "44px"
  icon-button:
    textColor: "{colors.text-2}"
    rounded: "{rounded.pill}"
    size: "44px"
  rail-button:
    textColor: "{colors.white}"
    typography: "{typography.glyph-count}"
    width: "56px"
    height: "52px"
  rail-button-primary:
    backgroundColor: "{colors.white}"
    textColor: "{colors.void}"
    rounded: "{rounded.pill}"
    size: "60px"
  tab:
    textColor: "{colors.text-3}"
    typography: "{typography.glyph-count}"
    width: "88px"
    height: "64px"
  tab-active:
    textColor: "{colors.white}"
  file-row:
    rounded: "{rounded.row}"
    padding: "8px"
    height: "64px"
  file-row-hover:
    backgroundColor: "{colors.slate}"
  sheet:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.white}"
    rounded: "{rounded.sheet}"
    padding: "20px 24px 24px"
  segmented:
    backgroundColor: "{colors.slate}"
    rounded: "{rounded.row}"
    padding: "3px"
  toast:
    backgroundColor: "{colors.white}"
    textColor: "{colors.void}"
    rounded: "{rounded.row}"
    padding: "12px 16px"
---

# Design System: RSVP Reader

## Overview

**Creative North Star: "One Thing Owns the Screen"**

A night-reading instrument. Every view hands the whole viewport to a single subject: on the Now feed it is one book, its cover blown up and blurred into the field behind it; in the reader it is one word, alone on the void. Interface chrome is white glyphs and quiet grey type that recede until summoned, and during playback they disappear entirely.

The palette is a cool near-black ladder with one hot accent. Colour in the content comes from the books themselves (cover art, per-book tone fields); colour in the interface is white, a few greys, and a single signal red that marks the pivot letter and the live position. Tall condensed caps carry titles and counts; a hyperlegible humanist sans carries the word and the surrounding text; system sans carries everything operational.

Density is low and thumb-led. Controls sit in a vertical rail at the lower right, the caption block sits lower left, and the top edge holds only orientation (wordmark and count, or back and the running chapter head). Motion is short and decelerating; nothing moves while words are playing.

**Key Characteristics:**
- Full-bleed single subject per viewport: snap feed of books, word on the void.
- Dark is the default; light theme recolours the pages and reader, but the Now feed stays night.
- White-on-dark glyph rail in the thumb zone, 1.5px outline icons, labels and counts beneath.
- Antonio condensed caps for titles and numerals, Atkinson Hyperlegible for reading, system sans for UI.
- One accent, signal red, spent only on the pivot letter and current-position marks.

## Colors

A cool, faintly blue near-black ladder, a warm paper inversion for light mode, and a single red that means "here".

### Primary
- **Signal Red** (signal; light theme: light-signal): the optical pivot letter of the current word, the current chapter number, and the text-selection tint. It never fills a button, never decorates, never appears on the feed. Light mode deepens it so it holds contrast on paper.

### Neutral
- **Void** (void): the ground of the app in dark mode and the permanent ground of the Now feed. The reader's word sits directly on it.
- **Ink** (ink): first raised layer; sheets, the context panel, empty-state slides.
- **Slate** (slate): second layer; hover fills on rows, segmented track, fallback tone behind covers, thumbnail wells.
- **Mist** (mist): hairlines and dividers, inactive track of sliders and progress bars, switch-off fill.
- **Guide Grey** (guide): fixation guides above and below the pivot; deliberately just above the void so they register without competing.
- **Ash** (text-2): secondary text; meta lines, sheet help copy, context paragraphs at rest. 8.4:1 on void.
- **Pewter** (text-3): tertiary text; running chapter head, section labels, tab labels at rest, the dimmed context sentence. 5.9:1 on void, 5.1:1 on slate.
- **Fog** (fog): a recorded world neutral; in the build it serves as tertiary text in light mode.
- **Bone White** (white): primary text and every interface glyph in dark mode; also the fill of the primary play button and solid buttons (inverse treatment).
- **Media Silver** (on-media-2): secondary text laid over cover art (author line, dim caption, feed count).
- **Sand** (sand): warm neutral on generated typographic covers (author line and rule) for books without art.
- **Paper / White Card / Linen / Rule / Graphite / Guide Sand** (light-bg, light-surface, light-surface-2, light-line, light-text-2, light-guide): the light theme ladder, warm instead of cool; Void becomes primary text.

### Named Rules
**The White Glyph Rule.** Interface colour is white (or its light-mode inversion, void) and grey. Hue in a surface comes from book covers and per-book tone fields, never from chrome.

**The Signal Is a Location Rule.** Signal red marks where the reader is (pivot letter, current chapter). If it is not a position, it is not red.

**The Feed Is Always Night Rule.** The Now feed, its overlay top bar, and the tab bar on that route stay on void with media-white text regardless of theme; cover art needs a dark field and a scrim to read.

## Typography

**Display Font:** Antonio 600 (with Arial Narrow, sans-serif)
**Reading Font:** Atkinson Hyperlegible 400 (with system-ui)
**UI Font:** system-ui stack

**Character:** Antonio gives poster-tall uppercase titles and numerals that sit like film credits over cover art; Atkinson is chosen for letterform distinctness at speed; the system stack keeps operational text native and weightless.

### Hierarchy
- **Display** (600, clamp 3.25-5.5rem, 0.9, uppercase): book title on a feed slide, max three lines, balanced wrap. Empty-state slide titles use the same voice slightly smaller.
- **Headline** (600, 3rem, 0.9, uppercase): page titles (Files, Pace). The Pace lede uses Antonio at clamp 2-3.25rem in Pewter with the figures in white.
- **Title** (600, 1.5-1.75rem, 1, uppercase): sheet titles, reader caption title, chapter heads in the context text.
- **Numeral** (600, 5rem, 0.9, tabular): the WPM readout; Antonio is also used for chapter numbers and the feed count.
- **Word** (Atkinson 400, clamp 2.4-4.75rem, 1.15): the RSVP word, split around the pivot.
- **Reading** (Atkinson 400, 1.0625rem, 1.65, max 65ch): surrounding text in the context panel.
- **Body** (system 400, 1rem, 1.5): file names, settings labels, captions (0.875-0.9375rem).
- **Label** (system 600, 0.75rem, 0.14em, uppercase): button text, running chapter head, section and panel labels, units.
- **Glyph count** (system 600, 0.6875rem, 0.04em, tabular): text under rail icons and tab icons (tabs add uppercase at 0.06em).

### Named Rules
**The Tall Caps Rule.** Antonio is always 600, always uppercase for words, always tight (0.9-1 line height). Numerals in Antonio use tabular figures.

**The Word Is Atkinson Rule.** Anything the user reads as text of the book (the RSVP word, context paragraphs) is Atkinson Hyperlegible; nothing operational is.

**The Tabular Pace Rule.** Every changing number (percent, time left, WPM, counts) uses tabular figures so it does not jitter.

## Layout

Phone-first, one subject per viewport. The Now feed is a vertical `scroll-snap` list of slides, each exactly viewport height minus the 64px tab bar and safe area. On phone a slide is a two-column grid: cover centred in the upper area, caption block lower left, rail lower right; 20px left gutter, 12px right. From 760px the gutters widen (48px / 32px). From 1100px a slide becomes three columns (cover, caption up to 560px, rail) bottom-aligned with a 56px column gap.

The reader is the word centred on the void, lifted 18dvh above centre so it sits above the thumb zone (12dvh on wide screens). Chrome is anchored to edges: back and chapter head at the top, caption lower left, rail lower right, scrubber on the bottom edge. Below 960px the surrounding text is a bottom sheet at 56dvh and the word lifts above it; at 960px and up it becomes a side panel of clamp(340px, 38vw, 560px).

List pages (Files, Pace) are a centred 760px column with 16px side padding, 24px top, and room cleared for the tab bar. Spacing rhythm clusters at 8, 14, 20, 24, 32 and 48px. Touch targets are at least 44px everywhere.

### Named Rules
**The Thumb Zone Rule.** Primary actions live in the lower-right rail; the top edge is for orientation only.

## Elevation & Depth

Mostly flat tonal layering (void, ink, slate) with soft ambient shadows reserved for things that physically float over content: the book cover above its blurred field, the play button over cover art, bottom sheets and the context sheet, toasts. Shadows are diffuse and black, never coloured, never offset hard. Over cover art, depth comes from the blur-and-darken field, a bottom-weighted scrim gradient, and a fine grain overlay (8% opacity) rather than from cards. On wide screens the context panel drops its shadow and sits beside the reader with a hairline.

### Shadow Vocabulary
- **Cover lift** (`0 30px 60px -20px rgb(0 0 0 / .8), 0 8px 18px rgb(0 0 0 / .35)`): the feed cover over its field.
- **Sheet** (`0 -20px 50px rgb(0 0 0 / .45)`): modal bottom sheets (the context sheet uses `0 -20px 40px rgb(0 0 0 / .35)`).
- **Float** (`0 6px 20px rgb(0 0 0 / .4)`): the primary play button over cover art; toasts use `0 10px 30px rgb(0 0 0 / .35)`.
- **Glyph lift** (`drop-shadow(0 1px 2px rgb(0 0 0 / .45))`): outline rail glyphs over cover art.

### Named Rules
**The Float Only Over Content Rule.** A shadow means the element is above other content. Elements in the reader, on the void, carry no shadow.

## Shapes

Small, nearly square corners on rectangular controls and covers (3-4px) so the system reads as typographic rather than bubbly; 10px on rows, toasts and segmented tracks; 16px top corners on sheets (18px on phone sheets); fully round for icon buttons, the play button, switches and slider thumbs. Lines are 1px hairlines in Mist; progress tracks are 2px (4px for the WPM slider). Icons are 24px outline glyphs at 1.5px stroke with round caps and joins, enlarged to 30px in the rail.

## Components

### Buttons
Tracked uppercase labels in small, nearly square boxes; confident but quiet.
- **Shape:** nearly square (3px), 44px tall, 18px side padding, optional 20px icon with 8px gap.
- **Solid:** inverse fill (white on void in dark, void on paper in light). Hover mixes 14% toward the ground. Disabled drops to Slate with Pewter text.
- **Quiet:** 1px Mist border, Ash text; hover brightens text to white and border to Pewter.
- **Media:** for use over cover art; translucent white fill (12%) with a 28% white hairline, hover to 20%.
- **Icon button:** 44px round, Ash glyph, hover adds an 8% white wash. A ringed variant adds a Mist hairline (WPM minus/plus).

### Rail (signature)
The vertical glyph rail in the lower right of feed slides and the reader.
- Each item is an outline icon (30px, 1.5 stroke) with a label or live count beneath in the glyph-count style; 14px gap between items; press scales to 0.92.
- The primary item is a 60px white disc with a filled void play/pause glyph; on the feed it carries a soft float shadow, in the reader it is flat.
- Engaged state (aria-pressed) thickens the stroke to 2.25 rather than changing colour.

### Navigation
Bottom tab bar, 64px plus safe area, three items (Now, Files, Pace) centred at 88px wide: icon over uppercase glyph-count label. Rest is Pewter, current is white with a 2px stroke. Translucent ground with a Mist top hairline; void on the Now route; hidden in the reader.

### Lists / Rows
File and chapter rows: 64px (52px compact) on a 10px radius, 44px thumbnail well, name in body 600, sub-line in Pewter with tabular figures. Rows are separated by an inset 1px Mist line that vanishes around the hovered row; hover fills with Slate; selected and current rows use an 8-10% white wash, and the current chapter number turns signal.

### Sheets
Native dialogs as bottom sheets on phone (18px top corners, grip bar, 86dvh max) and centred 16px cards from 700px. Ground Ink, Antonio title, 55% black backdrop. Enter by rising 40px while fading over 260ms.

### Inputs / Controls
- **Segmented:** Slate track, 3px inset, options at 38px; the checked option takes the ground colour with a 1px soft shadow.
- **Switch:** 48x28 pill, Mist off, white on with a void knob.
- **Sliders:** 2px (scrubber) or 4px (WPM) track filled white up to the value over Mist; round white thumb.
- **Focus:** 2px outline in the text colour, 2px offset, 6px radius, on every focusable element.

### Feed Slide (signature)
Blurred cover field (24px blur, 0.7 brightness, scaled to hide edges) with grain and a bottom scrim; the cover at 2:3 with cover lift; display title, tracked author line in Media Silver, caption "percent · time left · done by" with the finish time dimmed and shown only within six hours; a 2px progress hairline up to 420px wide. Books without art get a typographic cover: tone-field ground, Antonio title, Sand author and rule.

### Reader Word (signature)
The word is split into left, pivot and right spans so the pivot letter stays at a fixed centre; the pivot is signal, or Pewter at a pause/break. Two Guide Grey hairlines with 12px centre ticks frame it above and below. While playing, all chrome fades to zero (260ms) and the scrubber hides; tapping shows it again.

## Do's and Don'ts

### Do:
- **Do** give each viewport one subject: one book per feed slide, one word in the reader.
- **Do** keep interface glyphs white (dark) or void (light), with Ash and Pewter for secondary and tertiary text.
- **Do** reserve signal red for position: the pivot letter, the current chapter, the selection tint.
- **Do** put primary actions in the lower-right rail with labels or live counts under 1.5px outline glyphs.
- **Do** set titles and numerals in Antonio 600 uppercase at 0.9-1 line height, and any book text in Atkinson Hyperlegible.
- **Do** use tabular figures for every changing number.
- **Do** carry text over cover art with the blurred field, bottom scrim and grain, using media white and Media Silver.
- **Do** keep transitions at 200ms (260ms for sheets and chrome fades) on the decelerating ease, and stop all motion during playback.
- **Do** keep touch targets at 44px or larger.

### Don't:
- **Don't** add hue to chrome; colour comes from covers and tone fields.
- **Don't** use signal red for buttons, links, decoration or emphasis that is not a position.
- **Don't** add a bottom toolbar to the reader or move primary controls to the top edge.
- **Don't** put shadows on elements that sit on the void in the reader.
- **Don't** switch the Now feed to the light theme.
- **Don't** animate anything while words are playing.
