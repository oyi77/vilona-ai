# AGENTS.md — AI Coding Assistant Orientation

Auto-loaded by Claude Code and similar tools. Keep accurate.

## Project overview

Vilona AI is a **crypto/forex trading control platform** with two interacting parts:

1. **Python backend** (`/`) — `app_server.py` bridges CCXT/MT5, runs a FastAPI
   trading API on `:8300`, starts a polling Telegram bot, and manages a Rich TUI
   dashboard.
2. **Serverless Telegram bot** (`tgcloud-bot/`) — runs on Telegram's V8 isolate
   platform; registers users, stores exchange credentials, proxies `/status` and
   `/balance` to the Python backend via `OUTBOUND_URL`.

## Bot identity

| Name | Username | Token |
|------|----------|-------|
| BK-Trade Bot | `@agent_1ai2_bot` | `[REDACTED]:[REDACTED]` |

- Polling bot (Python): `vilona_TELEGRAM_BOT_TOKEN` in `.env`.
- Serverless bot: `TGCLOUD_TOKEN` in `tgcloud-bot/.env`; format `app<id>:<secret>`.

## Default admin

**Chat ID `[REDACTED]`** (`@[REDACTED]`) is the primary admin on the serverless
bot. The Python backend uses config-based `vilona_TELEGRAM_ADMIN_IDS`.

## Quick reference

```bash
# Python backend
python app_server.py                              # full boot
vilona_PAPER_TRADING=true vilona_HEADLESS=true python app_server.py  # paper

# Serverless bot
cd tgcloud-bot
TGCLOUD_TOKEN=... npx tgcloud push
TGCLOUD_TOKEN=... npx tgcloud migrate
npx tgcloud status

# Tests
python -m pytest tests/ -q
```

## Key files

| Path | Purpose |
|------|---------|
| `app_server.py` | Lifecycle: bridge → FastAPI → Telegram → dashboard |
| `config/__init__.py` | All `vilona_*` env vars → typed dataclass |
| `trading/trade_executor.py` | Order management, SL/TP, position sizing |
| `trading/news_guard.py` | News event risk gate |
| `trading/session_guard.py` | Session-hour risk gate |
| `llm/client.py` | Async LLM with SSE streaming |
| `llm/endpoints.py` | SSE endpoint definitions |
| `core/runtime.py` | RuntimeSupervisor — scan loop + event recording |
| `ui/user_registry.py` | Multi-user SQLite store |
| `ui/auth.py` | `is_authorized()`, `is_admin()` helpers |
| `ui/telegram_controller.py` | Legacy polling Telegram bot |
| `tgcloud-bot/tgcloud/handlers/message.js` | Serverless command router |
| `tgcloud-bot/tgcloud/schema.js` | Serverless DB schema |
| `armada/` | Autonomous agent hub + worker + governor |
| `tests/` | 29 pytest tests (no credentials needed) |

## Rules

- **Paper first** — `vilona_PAPER_TRADING=true` is the default. Real trading
  requires explicit opt-in.
- **No secrets in git** — `.env`, `*.session`, `TGCLOUD_TOKEN`, bot tokens,
  exchange API keys are all gitignored.
- **Serverless bot deploy** — always `push` then `migrate`. Deploy never touches
  the DB; migration is a separate step.
- **Test before merge** — E2E with `[REDACTED]` Telethon session
  (`~/.telethon_session/[REDACTED].session`) + API ID `[REDACTED]` / hash
  `[REDACTED]`.

## E2E testing

```bash
export TELETHON_SESSION="$HOME/.telethon_session/[REDACTED].session"
export TELEGRAM_API_ID="[REDACTED]"
export TELEGRAM_API_HASH="[REDACTED]"
export TELETHON_BOT_USERNAME="agent_1ai2_bot"
python test_live_bot.py   # or any telethon-based test
```

Flow: `/start` → pending → admin `/approve <chat_id>` → approved commands work.
