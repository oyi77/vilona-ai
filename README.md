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

Commands (`@agent_1ai2_bot`):
| Command | Who | Description |
|---------|-----|-------------|
| `/start` | all | Register / re-login |
| `/help` | approved | Command reference |
| `/status` | approved | Positions + daily P&L (proxied to Python backend) |
| `/balance` | approved | Account balance (proxied to backend) |
| `/setkeys <ex> <key> <secret>` | approved | Store exchange credentials |
| `/setbackend <url>` | admin | Set Python backend URL |
| `/users` | admin | List registered users |
| `/approve <chat_id>` | admin | Approve pending registration |
| `/decline <chat_id>` | admin | Remove pending user |

**First registrant is auto-approved as admin.** Admin sets the Python backend URL via `/setbackend http://your-host:8300` so `/status` and `/balance` can proxy through.

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
