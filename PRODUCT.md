# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Primary: the author, reading his own library on a self-hosted server over Tailscale. Main scene is a phone in the evening or in bed: dim room, one hand, short-to-medium sessions. Desktop is secondary. Others may self-host it from the public GHCR image; they are welcome but not designed for (no onboarding funnel, no accounts).

## Product Purpose

Get through books faster. RSVP (one word at a time, fixed fixation point) removes eye travel so the reader can sustain high WPM on non-fiction and backlog. Success: more books finished, with a clear sense of pace (time left, words read) and zero friction resuming on any device.

## Positioning

Self-hosted, single container, reads the files you already have (EPUB, MOBI/AZW/AZW3, PDF, TXT, MD) straight from a folder. No accounts, cloud, telemetry, or import step. Progress syncs across devices because it lives on your own server.

## Operating Context

- Accessed by browser over a tailnet, typically plain HTTP on a port (HTTPS only if the user sets up `tailscale serve`).
- Books live in a mounted folder; browsing reads it live.
- Reading loop: open app, resume from Continue Reading, play, pause to re-orient in the surrounding text, close. Cross-device resume is routine.

## Capabilities and Constraints

- Backend: Python 3.12 / Flask, SQLite for progress and stats, JSON text cache.
- Frontend: vanilla HTML/CSS/JS, no build step, no npm. Must stay light and fast on a phone; this is a hard constraint.
- RSVP with ORP pivot alignment, punctuation-aware pacing, pause-to-context panel with click-to-seek, chapters, WPM 100-800, adjustable word size.
- No auth by design; security relies on the network (Tailscale). Filesystem access is confined to a configured root.

## Evidence on Hand

No screenshots, testimonials, or usage data. Nothing to cite publicly; do not invent claims.

## Product Principles

1. The word is the product. During playback nothing else competes for attention.
2. Pace is visible. Time left and progress are always one glance away when paused.
3. Resume is instant. From opening the app to reading should be one tap.
4. Light by construction. No frameworks or heavy assets; it must feel instant on a phone.
5. Your files, your server. No import, no lock-in, no outbound calls.

## Accessibility & Inclusion

Comfortable in a dark room (no bright flashes, low-glare dark default while honoring system preference). Full keyboard operation on desktop; 44px touch targets on phone. Respect `prefers-reduced-motion`.
