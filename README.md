# RSVP Reader

A self-hosted, browser-based RSVP (Rapid Serial Visual Presentation) reading app. One word at a time, at configurable speed. Tracks your progress per book across devices.

## What it does

- Browses a folder of books (EPUB, PDF, TXT, Markdown)
- Flashes one word at a time with Optimal Recognition Point (ORP) alignment
- Saves your reading position server-side — resume on any device
- "Continue Reading" dashboard with progress bars
- Dark/light theme, 100–1000 WPM, keyboard shortcuts

## Running

### Prerequisites
- Docker with the Compose plugin (`docker compose version`)

### Start

```bash
docker compose up --build -d
```

Then open `http://<your-server-ip>:5002` in a browser.

### Stop / restart

```bash
docker compose down
docker compose up -d
```

### Update (after pulling new code)

```bash
docker compose up --build -d
```

The `--build` flag rebuilds the image with any code changes. Your data is in `./data/` and is unaffected.

## Adding books

Drop files into your books folder (configured as the volume mount in `docker-compose.yml`). The browse view reads the directory live — no scan or import step needed. Supported formats: `.epub`, `.pdf`, `.txt`, `.md`.

## Keyboard shortcuts (player view)

| Key | Action |
|-----|--------|
| `Space` | Play / Pause |
| `←` / `→` | Back / Forward 10 words |
| `Shift+←` / `Shift+→` | Back / Forward 50 words |

## Backing up your progress

Progress is stored in `./data/progress.db` (SQLite). To back it up:

```bash
cp ./data/progress.db ./data/progress.db.bak
```

Or copy it off the server:

```bash
scp yourserver:/path/to/rsvp-reader/data/progress.db .
```

Text extraction caches are in `./data/text_cache/`. They are safe to delete — they will be regenerated on next open. Only `progress.db` contains data you can't recover.

## Tailscale access

1. Find your server's Tailscale IP: `tailscale ip -4`
2. Open `http://<tailscale-ip>:5002` from any device on your tailnet.
3. If MagicDNS is enabled, you can also use `http://<hostname>:5002` where `<hostname>` is the machine name shown in the Tailscale admin panel.

No authentication is needed — Tailscale handles access control. Do not expose port 5002 to the public internet.

## Configuration

Environment variables (set in `docker-compose.yml`):

| Variable | Default | Description |
|----------|---------|-------------|
| `BOOKS_DIR` | `/books` | Path inside container where books are mounted |
| `DATA_DIR` | `/app/data` | Path inside container for SQLite DB and text cache |
| `PORT` | `5002` | Port Flask listens on |
| `TZ` | `America/Denver` | Timezone for timestamps |
# RSVP-reader
