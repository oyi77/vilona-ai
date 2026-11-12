# AGENTS.md — AI Coding Assistant Orientation

Auto-loaded by Claude Code and similar tools. Keep accurate.

## Project overview

Vilona AI is a **crypto/forex trading control platform** with three parts sharing
one central relay:

1. **Central relay** (`license_server.py`) — holds licenses, device registry,
   command queue, and events. Single SQLite DB, serves `X-Relay-Token` (bot)
   and Bearer (device) auth.
2. **Python backend / desktop binary** (`app_server.py` + `client/client.py`) —
   bridges CCXT/MT5, hosts an embedded `RelayClient` (outbound only) that polls
   for commands and reports state. Also runs a FastAPI trading API on `:8300`,
   a polling Telegram bot, and a Rich TUI dashboard.
3. **Serverless Telegram bot** (`tgcloud-bot/`) — master-control UI. Registers
   users, pairs devices, and routes `/status`, `/balance`, and runtime commands
   through the relay queue.

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
| `app_server.py` | Lifecycle: bridge → FastAPI → Telegram → dashboard → relay client |
| `config/__init__.py` | All `vilona_*` env vars → typed dataclass |
| `license_server.py` | Self-hosted license server **+ central relay** (devices/commands/events) |
| `client/client.py` | Desktop relay client (outbound poll → execute → report) |
| `trading/trade_executor.py` | Order management, SL/TP, position sizing |
| `trading/news_guard.py` | News event risk gate |
| `trading/session_guard.py` | Session-hour risk gate |
| `llm/client.py` | Async LLM with SSE streaming |
| `llm/endpoints.py` | SSE endpoint definitions |
| `core/runtime.py` | RuntimeSupervisor — scan loop + event recording |
| `core/account_license.py` | Per-MT5-account licensing |
| `ui/user_registry.py` | Multi-user SQLite store |
| `ui/auth.py` | `is_authorized()`, `is_admin()` helpers |
| `ui/telegram_controller.py` | Legacy polling Telegram bot |
| `tgcloud-bot/tgcloud/handlers/message.js` | Serverless command router (drives relay) |
| `tgcloud-bot/tgcloud/schema.js` | Serverless DB schema |
| `armada/` | Autonomous agent hub + worker + governor |
| `tests/` | pytest suite (37 tests, no credentials needed) |

## Rules

- **Paper first** — `vilona_PAPER_TRADING=true` is the default. Real trading
  requires explicit opt-in.
- **Outbound only** — desktop binaries never listen on a port; they poll the
  central relay. Production relay MUST sit behind TLS/reverse proxy.
- **No secrets in git or chat** — `.env`, `*.session`, `TGCLOUD_TOKEN`, bot
  tokens, exchange API keys are gitignored. Exchange keys live ONLY on the
  user's desktop; the bot never accepts them in Telegram.
- **Tenant isolation** — relay scopes every command/event/status query strictly
  by `chat_id`; device tokens are SHA-256 hashed and returned once at `/pair`.
- **Serverless bot deploy** — always `push` then `migrate`. Deploy never touches
  the DB; migration is a separate step.
- **Test before merge** — E2E with Telethon session + unit/integration tests
  (`tests/test_relay.py`, `tests/test_relay_client.py`).

## E2E testing

```bash
export TELETHON_SESSION="$HOME/.telethon_session/[REDACTED].session"
export TELEGRAM_API_ID="[REDACTED]"
export TELEGRAM_API_HASH="[REDACTED]"
export TELETHON_BOT_USERNAME="agent_1ai2_bot"
python test_live_bot.py   # or any telethon-based test
```

Flow: `/start` → pending → admin `/approve <chat_id>` → approved commands work.
