# Vilona AI v2 UI and operations notes

**Updated:** 2026-11-10
**Status:** Reflects the current repository, not a future implementation plan

## Product boundary

Vilona AI exposes monitoring and control surfaces around exchange bridges and now includes a lifecycle-owned `RuntimeSupervisor`. `app_server.py` connects one bridge, creates paper or live execution through an explicit adapter, starts the Telegram controller when a bot token is configured, and starts the Rich terminal dashboard. Autonomous scanning is opt-in and remains disabled by default.

The UI must distinguish stopped, running, degraded, and emergency-stopped runtime states. A missing signal provider produces `WAIT`; stale ticks produce a fault rather than an order. Paper execution never calls a broker order method.

## Telegram command center

The persistent menu contains four views:

- **Status** shows open positions, daily P&L, win/total count, and up to ten open trades.
- **Balance** uses the bridge’s normalized `get_balance()` API. CCXT returns the configured USDT total/free wallet values. MT5 returns balance, equity, margin, and free margin.
- **Control** shows paper/live mode and the configured exchange. Start, stop, and restart are admin-only state controls.
- **Health** shows runtime state, bridge/database/LLM health, uptime, error count, last scan age, and emergency-latch state.
- **Events** shows recent append-only SQLite runtime events.
- **Logs** shows the controller’s in-memory recent log list. It is not a historical SQLite log viewer.

Viewer access comes from `vilona_TELEGRAM_CHAT_IDS`. Admin access comes from `vilona_TELEGRAM_ADMIN_IDS`. The admin list must be a subset of the viewer list. An empty list fails closed. Close-all requires an admin and two actions: request confirmation, then select “Yes, close all”. The confirmation handler calls `bridge.close_position()` for each position and reports partial failures.

Telegram MarkdownV2 formatting is escaped through `ui.prompts.escape_md_v2`. When adding a new view, keep all user-controlled symbols, reasons, and error messages escaped before interpolation.

### Command matrix

Viewer commands are `/status`, `/health`, `/events [count]`, `/balance`, `/control`, `/logs`, and `/help`. Admin commands are `/start_scan`, `/stop_scan`, `/restart_scan`, `/emergency_stop [reason]`, and `/emergency_reset`. Emergency stop is intentionally immediate; reset is confirmation-gated and never starts the runtime. Control and destructive callbacks are bound to the requesting chat, single-use, and expire after 30 seconds.

## Terminal dashboard

The dashboard is intentionally lightweight and uses Rich rather than a GUI toolkit. Its header shows the configured paper/live mode and exchange and reads daily P&L through the shared `calculate_daily_pl(symbol)` bridge method. Its footer shows uptime, open-position count, and mode. Activity logs are in-memory and capped at 50 entries.

The dashboard observes the shared runtime state. Telegram Start and Stop call the supervisor, while Close All remains a separate admin-confirmed action.

## Desktop tray

`ui/system_tray.py` is an optional Windows presence layer using `pystray` and Pillow. The current tray callbacks update local status, open Telegram, show a position count, and emit best-effort notifications. They are not a second execution engine. PyQt6 is a separate desktop panel and is not started by `app_server.py`.

## Runtime and execution service

The supervisor implements these boundaries:

1. Fetch tick and candles for one symbol and configured timeframes.
2. Build a `MarketSnapshot` and optionally call researcher/trader LLM roles.
3. Apply `risk_manager.evaluate()` before any order call.
4. Require an explicit judge approval when the judge role is enabled.
5. In paper mode, record the proposed order without sending it to the bridge.
6. In live mode, call `send_market_order()` and persist the result.
7. Run break-even, trailing, and drift-cancellation maintenance separately from signal generation.
8. Publish alert messages only after an observed order/persistence result.

Each scan is idempotency-keyed by symbol and scan bucket. Decisions and execution outcomes are appended to SQLite runtime events. `vilona_EMERGENCY_STOP_FILE` causes the supervisor to enter `emergency_stopped`; remove the file and explicitly reset the runtime before restarting. Live CCXT spot position close and synthetic SL/TP emulation are rejected by the adapter rather than silently approximated.

## Configuration source of truth

The dataclasses in `config/__init__.py` and `.env.example` are authoritative. Environment variables use the `vilona_` prefix. The older `KINGAI_` examples and `authorized_users`/`admin_users` names are obsolete and should not be reintroduced.
