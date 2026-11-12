# Vilona AI v2

AI-powered crypto trading agent — Python backend + serverless Telegram bot.

```
python app_server.py          # Python backend (FastAPI on :8300 + polling Telegram bot)
cd tgcloud-bot && npm run deploy   # Serverless Telegram Mini App bot
```

## What it does

- **Trading**: CCXT (crypto) and MetaTrader 5 (forex) bridges — market data, positions, orders, SL/TP, P&L.
- **Intelligence**: LLM-powered signal generation, risk gating, SSE streaming chat, model routing, budget controls.
- **Telegram command center**: serverless bot (`@agent_1ai2_bot`) — registration, per-user exchange credentials, admin approval flow, trading data proxy to Python backend.
- **Terminal dashboard**: Rich TUI with paper/live mode, daily P&L, position count, colored logs.
- **Runtime supervisor**: cancellable scan loop, stale-data rejection, risk guards, event recording, emergency stop.

## Quick start

```bash
git clone https://github.com/oyi77/vilona-ai.git
cd vilona-ai
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# fill in .env — then:
python app_server.py
```

Paper mode (headless, no credentials needed):
```bash
export vilona_PAPER_TRADING=true vilona_HEADLESS=true vilona_EXCHANGE=binance
python app_server.py
```

## Project layout

```
app_server.py              Runtime lifecycle — bridge, FastAPI, Telegram controller, dashboard
config/__init__.py         Dataclass config + env parsing (vilona_* prefix)

# Trading
trading/                   Bridge adapters, trade executor, risk guards, session guard,
                           signal gatekeeper, economic calendar, news guard, performance
data/king_signals.csv      Signal reference data

# LLM / AI
llm/                       Client, SSE endpoints, Anthropic adapter, model router,
                           budget controls, reasoning module
core/account_license.py    License client
core/secure_store.py       Encrypted credential storage

# User management
ui/user_registry.py        SQLite-backed multi-user registration & session store
ui/auth.py                 Auth helpers (is_authorized, is_admin)

# Telegram (polling — runs with app_server.py)
ui/telegram_controller.py  Legacy polling bot (python-telegram-bot >=21)

# Telegram (serverless — deploy to Telegram infra)
tgcloud-bot/               Serverless bot project (Node, deploy via tgcloud CLI)
  tgcloud/schema.js        DB schema: users + per-user exchange credentials
  tgcloud/handlers/       Update handlers (message, callback_query, …)
  tgcloud/endpoints/      Mini App server-side endpoints

# Runtime / persistence
core/runtime.py           RuntimeSupervisor, event recording, health snapshots
core/state_db.py          Thread-safe SQLite persistence
core/market_cache.py      Market data cache

# Desktop
ui/terminal_dashboard.py  Rich TUI dashboard
ui/system_tray.py         Optional Windows system tray (pystray)

# Utilities
armada/                   Hub, worker, governor, protocol, model — autonomous agents
agents/                   Signal, research, risk, judge modules
core/i18n*.py             i18n strings

tests/                    pytest suite (29 tests, no credentials needed)
Dockerfile                Headless paper-mode container
docs/UX_DESIGN.md         UX & ops notes
```

## Multi-tenancy architecture

Three parts, one source of truth (the central relay DB):

```
  Telegram user ──► TGCloud bot ──┐        (master-control UI, outbound fetch)
                                  ▼
                          Central relay  ◄── license + devices + commands + events
                                  ▲           (license_server.py, one service)
  User's desktop binary ──────────┘        (outbound ONLY: poll → execute → report)
                                          (own MT5/CCXT, own keys, never exposed)
```

- Every user downloads the desktop binary; it **phones home outbound** to the
  relay (no inbound ports on the user's machine).
- The Telegram bot issues commands (`/start_scan`, `/status`, …) which the relay
  queues per-device; the desktop polls, executes against its **own** MT5, and
  writes results/state back. Both Telegram and desktop read the same DB, so
  status stays in sync.
- Licensing is enforced per MT5 account: `runtime.start` is refused for
  unlicensed devices at both server and client.

Run the relay (production: behind TLS/reverse proxy):

```bash
export vilona_RELAY_BOT_TOKEN=<secret>       # bot↔server auth, server-side only
export vilona_LICENSE_ADMIN_TOKEN=<secret>   # license admin API
python license_server.py                      # binds :8301, serves /license/* + /relay/*
```

Pair a desktop client: send `/pair <name>` to the bot, copy the one-time token
into the desktop app (`vilona_RELAY_DEVICE_TOKEN`), set `vilona_RELAY_URL=https://…`,
restart the app. The app registers, checks its license, and begins polling.

## Serverless Telegram bot

The `tgcloud-bot/` sub-project runs on Telegram's serverless platform. Deployed with:

```bash
cd tgcloud-bot
npm install
npx tgcloud login   # link your bot (platform token, not Telegram bot token)
npx tgcloud push     # deploy schema + handlers
npx tgcloud migrate  # apply schema changes
npx tgcloud status   # verify deployment
```

Set env on the deployed bot: `RELAY_URL`, `RELAY_BOT_TOKEN` (same value as the
server's `vilona_RELAY_BOT_TOKEN`).

Commands (`@agent_1ai2_bot`):
| Command | Who | Description |
|---------|-----|-------------|
| `/start` | all | Register / re-login |
| `/help` | approved | Command reference |
| `/pair <name>` | approved | Generate a one-time desktop pairing token |
| `/devices` | approved | Paired desktops + license + last-seen |
| `/license` | approved | License status of your devices |
| `/status` | approved | Queue a status read (async, from your desktop) |
| `/balance` | approved | Queue a balance read (async) |
| `/start_scan` | approved | Start the trading engine on your desktop |
| `/stop_scan` | approved | Stop the engine |
| `/emergency_stop` | approved | Immediately halt |
| `/emergency_reset` | admin | Clear the emergency latch |
| `/setkeys` | approved | Info: keys are configured locally in the desktop app |
| `/users` | admin | List registered users |
| `/approve <chat_id>` | admin | Approve pending registration |
| `/decline <chat_id>` | admin | Remove pending user |

**First registrant is auto-approved as admin.** Exchange/API keys are never sent
through Telegram — they live only on the user's desktop binary.

## Configuration

All variables use the `vilona_` prefix. See `.env.example` for the full list. Key variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `vilona_PAPER_TRADING` | `true` | Paper mode (no real orders) |
| `vilona_HEADLESS` | `false` | Skip TUI/dashboard |
| `vilona_EXCHANGE` | `binance` | Exchange name |
| `vilona_TELEGRAM_BOT_TOKEN` | empty | Polling bot token |
| `vilona_TELEGRAM_CHAT_IDS` | empty | Legacy viewer allowlist |
| `vilona_TELEGRAM_ADMIN_IDS` | empty | Legacy admin list |
| `vilona_AUTONOMY_ENABLED` | `false` | Start scan loop on boot |

**Safety:** default is paper trading. Set `vilona_PAPER_TRADING=false` only after reviewing the bridge behavior.

## Tests

```bash
python -m pytest tests/ -q
# 29 tests, no credentials or network required
```

## Deployment

- **Direct**: `python app_server.py` — use `scripts/run_vilona.sh paper` for managed paper runs.
- **Docker**: `docker build .` — starts headless paper mode by default.
- **Systemd**: `scripts/vilona.service` — edit user/path, then `sudo systemctl link` and `start`.
- **Serverless bot**: `cd tgcloud-bot && npm run deploy`
