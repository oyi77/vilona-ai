# Vilona AI v2

Vilona AI is a Python trading-control service for crypto exchanges supported by [CCXT](https://github.com/ccxt/ccxt) and for MetaTrader 5. It provides a Telegram command center, a Rich terminal dashboard, optional Windows tray controls, SQLite state, and fail-closed risk/persona helpers.

> **Safety:** The default is paper trading. This project can place real orders when `vilona_PAPER_TRADING=false`; review the configuration and bridge behavior before enabling live trading. It is not financial advice.

## Current capabilities

- CCXT and MetaTrader 5 bridges for market data, positions, orders, SL/TP, cancellation, balances, and daily P&L.
- Telegram views for status, balance, controls, and recent logs. Start/stop/restart and close-all are admin-only; close-all uses an explicit confirmation step.
- Rich terminal monitoring with paper/live mode, exchange name, daily P&L, open-position count, and colored activity logs.
- Risk helpers for confidence, spread, position count, daily loss, ATR-derived SL/TP, position sizing, break-even, trailing stops, and drift cancellation.
- Optional researcher, trader, risk-manager, and judge prompt/parser modules, plus an async LLM client.
- SQLite persistence and Docker, systemd, shell-runner, and Nuitka build support.
- Paper-first `RuntimeSupervisor` with cancellable scans, stale-data rejection, risk gating, event recording, health state, and an emergency-stop file.
- Explicit paper/live execution adapters. Paper mode never calls a broker order method.

## Runtime boundary

`RuntimeSupervisor` now orchestrates candle collection → signal provider → risk gate → optional judge → paper/live execution on a recurring interval. It is stopped by default; enable it with `vilona_AUTONOMY_ENABLED=true`. Without an LLM key or injected provider, the safe signal is `WAIT`. Daily reports, proactive alerts, and production-grade broker reconciliation remain separate follow-up work.

## Quick start

```bash
git clone https://github.com/oyi77/vilona-ai.git
cd vilona-ai
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
cp .env.example .env
python app_server.py
```

The application reads environment variables directly; it does not currently load `.env` files automatically. Export the variables from your shell or use a process manager with `EnvironmentFile` support. For a paper-mode local run:

```bash
export vilona_PAPER_TRADING=true
export vilona_EXCHANGE=binance
export vilona_HEADLESS=true
python app_server.py
```

Live mode requires exchange credentials, Telegram credentials and authorized chat IDs, and an LLM key according to `Config.validate()`. Keep `vilona_EXCHANGE_SANDBOX=true` while testing an exchange API integration.

For smaller deployments, install `requirements-core.txt` for headless operation. Add `requirements-mt5.txt`, `requirements-desktop.txt`, or `requirements-build.txt` only when those capabilities are needed. Autonomous scanning remains opt-in with `vilona_AUTONOMY_ENABLED=true`.

## Configuration and access control

`.env.example` is the canonical variable list. All variables use the lowercase `vilona_` prefix. `vilona_TELEGRAM_CHAT_IDS` is the viewer allow-list. `vilona_TELEGRAM_ADMIN_IDS` must be a subset of that list and controls scanner actions and close-all. An empty list denies Telegram access rather than implicitly authorizing a user.

Configuration is validated before a bridge is started. Secrets are masked by `Config.to_json()` and `Config.to_dataclass()`; do not commit `.env` or API credentials.

## Project layout

```text
app_server.py                 Runtime lifecycle and bridge/UI startup
config/__init__.py            Dataclass configuration and env parsing
trading/bridge_ccxt.py        CCXT adapter
trading/bridge_mt5.py         MetaTrader 5 adapter
trading/trade_executor_v2.py  Protective trade-management helpers
agents/                       Signal, research, risk, and judge modules
llm/client.py                 Async OpenAI-compatible/Anthropic client
ui/telegram_controller.py     Telegram command center
ui/terminal_dashboard.py      Rich terminal dashboard
ui/system_tray.py             Optional Windows tray integration
core/state_db.py              Thread-safe SQLite persistence
core/runtime.py               Cancellable scan/execution supervisor
trading/execution.py          Paper/live execution ports and adapters
core/events.py                Append-only runtime event model
core/health.py                Runtime health snapshots
tests/                        Offline smoke and integration tests
docs/                         UX and operations notes
```

## Tests and checks

```bash
python -m compileall -q .
python -m pytest -q
```

The tests use in-memory fake bridges and do not require exchange credentials or network access. Install the project dependencies and `pytest` in the active virtual environment before running them.

## Deployment

- `python app_server.py` starts the service directly.
- `scripts/run_vilona.sh paper` creates/uses `.venv`, installs dependencies, and writes logs under `logs/`.
- `Dockerfile` starts a headless paper-mode container by default. Mount persistent storage if the SQLite database must survive replacement.
- Edit `scripts/vilona.service` for the target Unix user and absolute project path before installation.
- `scripts/build.py` and `.github/workflows/build.yml` build platform artifacts with Nuitka.

## License

The repository describes the new code as MIT licensed. Add or retain a root `LICENSE` file before publishing a distributable release so the license is explicit to GitHub and downstream users.
