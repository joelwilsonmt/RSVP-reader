# RSVP Reader

A self-hosted, browser-based speed reader. Opens EPUB, PDF, TXT, and Markdown files and flashes one word at a time using **Rapid Serial Visual Presentation (RSVP)** — the same technique used by apps like Spritz and Spreeder.

Runs as a single Docker container. No accounts, no cloud, no telemetry. Access it from any device on your [Tailscale](https://tailscale.com) network.

---

## Features

- **RSVP playback** — 100–1000 WPM, configurable
- **Optimal Recognition Point (ORP)** alignment — the key character of each word is fixed to a horizontal pivot, reducing eye movement
- **Smart pacing** — longer delays after punctuation and paragraph breaks
- **Context panel** — pausing slides in a scrollable view of surrounding text; click any word to jump there
- **Cross-device progress** — position is saved server-side; resume on your phone where you left off on desktop
- **Continue Reading** dashboard with progress bars
- **Folder & file picker** — browse your server's filesystem from the UI
- **Dark / light theme**
- Supports `.epub`, `.mobi`, `.azw`, `.azw3`, `.pdf`, `.txt`, `.md`

---

## Quick Deploy

### Prerequisites

- A Linux server (home server, VPS, Raspberry Pi, etc.)
- [Docker](https://docs.docker.com/engine/install/) with the Compose plugin
- [Tailscale](https://tailscale.com) installed on the server and your devices (optional but recommended)

### 1. Create the project folder

```bash
mkdir ~/rsvp-reader && cd ~/rsvp-reader
```

### 2. Create `docker-compose.yml`

```yaml
services:
  rsvp:
    image: ghcr.io/joelwilsonmt/rsvp-reader:latest
    ports:
      - "5002:5002"
    volumes:
      - /mnt:/books:ro      # ← change to your books folder
      - ./data:/app/data
    environment:
      - TZ=America/Denver   # ← change to your timezone
      - BOOKS_DIR=/books
      - DATA_DIR=/app/data
    restart: unless-stopped
```

Or clone this repo and edit the included `docker-compose.yml`:

```bash
git clone https://github.com/joelwilsonmt/RSVP-reader.git ~/rsvp-reader
cd ~/rsvp-reader
# edit docker-compose.yml: set your books path and timezone
```

### 3. Start the container

```bash
docker compose up -d
```

Docker pulls the pre-built image from GitHub Container Registry — no build step needed.

### 4. Open in a browser

```
http://localhost:5002
```

Or from any device on your Tailscale network:

```
http://<server-tailscale-ip>:5002
http://<server-hostname>:5002   # if MagicDNS is enabled
```

Run `tailscale ip -4` on the server to find its Tailscale IP.

---

## Adding Books

Drop files into the folder you mounted as `/books`. The browse view reads the directory live — no import or scan step needed. Subfolders are supported.

Supported formats: `.epub`, `.mobi`, `.azw`, `.azw3`, `.pdf`, `.txt`, `.md`

You can also change the books root at any time from the UI: click the **📂 folder pill** in the top-left of the home screen to open a filesystem browser.

---

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Space` | Play / Pause |
| `←` / `→` | Back / Forward 10 words |
| `Shift+←` / `Shift+→` | Back / Forward 50 words |

---

## Updating

```bash
docker compose pull
docker compose up -d
```

This pulls the latest image and restarts the container. Your `data/` folder (progress database, text cache) is unaffected.

---

## Backup

All persistent state lives in `./data/progress.db` (SQLite). The text cache in `./data/text_cache/` is derived from your books and can be safely deleted — it will be regenerated on next open.

```bash
# local backup
cp ./data/progress.db ./data/progress.db.bak

# copy off-server
scp yourserver:~/rsvp-reader/data/progress.db .
```

---

## Building Locally

If you want to modify the code:

```bash
git clone https://github.com/joelwilsonmt/RSVP-reader.git
cd RSVP-reader
# edit docker-compose.yml: replace `image:` line with `build: .`
docker compose up --build -d
```

Every push to `main` automatically builds a new image via GitHub Actions and pushes it to `ghcr.io/joelwilsonmt/rsvp-reader:latest` (both `linux/amd64` and `linux/arm64`).

---

## Stack

- **Python 3.12** / **Flask** — backend
- **ebooklib** + **BeautifulSoup4** — EPUB extraction
- **pypdf** — PDF extraction
- **SQLite** — reading progress
- Vanilla HTML + CSS + JS frontend — no build step, no npm
