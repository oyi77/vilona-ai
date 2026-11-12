#!/usr/bin/env bash
# Demo: Vilona AI v2 — Python boot + serverless bot deploy + live Telegram test
# Usage: asciinema rec --command "bash demo.sh" --title "Vilona AI v2 demo" demo.cast
set -e
export PATH="$HOME/.local/bin:$PATH"
cd "$(dirname "$0")"

echo "=== Vilona AI v2 — Demo ==="
echo

echo "--- 1. Run tests ---"
python -m pytest tests/ -q 2>&1 | tail -3
echo

echo "--- 2. Boot Python backend (paper mode, 6s) ---"
export vilona_PAPER_TRADING=true vilona_HEADLESS=true vilona_EXCHANGE=binance
timeout 6 python app_server.py 2>&1 | head -8 || true
echo

echo "--- 3. Deploy serverless Telegram bot ---"
cd tgcloud-bot
TGCLOUD_TOKEN="${TGCLOUD_TOKEN:-$(grep TGCLOUD_TOKEN .env 2>/dev/null | cut -d= -f2)}" \
  ./node_modules/.bin/tgcloud status 2>&1 | head -6
echo

TGCLOUD_TOKEN="${TGCLOUD_TOKEN:-$(grep TGCLOUD_TOKEN .env 2>/dev/null | cut -d= -f2)}" \
  ./node_modules/.bin/tgcloud push 2>&1 | tail -5
echo

TGCLOUD_TOKEN="${TGCLOUD_TOKEN:-$(grep TGCLOUD_TOKEN .env 2>/dev/null | cut -d= -f2)}" \
  ./node_modules/.bin/tgcloud migrate --dry-run 2>&1
echo
cd ..

echo "--- 4. Live Telegram test via Telethon -> @agent_1ai2_bot ---"
timeout 60 python test_live_bot.py 2>&1 | head -25 || true
echo

echo "=== Demo complete ==="