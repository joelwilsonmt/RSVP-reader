#!/usr/bin/env bash
# Regenerate the PWA icons in static/icons from tools/icon.html using headless Chrome.
set -euo pipefail
cd "$(dirname "$0")/.."
CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
SRC="file://$PWD/tools/icon.html"
render() {  # size query out
  "$CHROME" --headless --disable-gpu --hide-scrollbars --allow-file-access-from-files \
    --virtual-time-budget=2000 --window-size="$1,$1" --screenshot="$PWD/static/icons/$3" "$SRC?size=$1$2" 2>/dev/null
}
render 192 "" icon-192.png
render 512 "" icon-512.png
render 512 "&mask=1" icon-maskable-512.png
render 180 "&mask=1" apple-touch-icon.png
render 96 "" icon-96.png
