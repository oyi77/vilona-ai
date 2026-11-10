# Vilona AI v2 UI and operations notes

**Updated:** 2026-11-10
**Status:** Reflects the current repository, not a future implementation plan

## Product boundary

Vilona AI currently exposes monitoring and control surfaces around exchange bridges. `app_server.py` connects one bridge, starts the Telegram controller when a bot token is configured, and starts the Rich terminal dashboard. It does not currently run an autonomous recurring scan loop or submit signals produced by the agent modules.

The UI must therefore describe the service as a control and observability layer until the scan/execution orchestrator is added. In particular, “AI trade alerts”, “daily reports”, and “automatic trading” are not delivered by the current server lifecycle.

## Telegram command center

The persistent menu contains four views:

- **Status** shows open positions, daily P&L, win/total count, and up to ten open trades.
- **Balance** uses the bridge’s normalized `get_balance()` API. CCXT returns the configured USDT total/free wallet values. MT5 returns balance, equity, margin, and free margin.
- **Control** shows paper/live mode and the configured exchange. Start, stop, and restart are admin-only state controls.
- **Logs** shows the controller’s in-memory recent log list. It is not a historical SQLite log viewer.

Viewer access comes from `vilona_TELEGRAM_CHAT_IDS`. Admin access comes from `vilona_TELEGRAM_ADMIN_IDS`. The admin list must be a subset of the viewer list. An empty list fails closed. Close-all requires an admin and two actions: request confirmation, then select “Yes, close all”. The confirmation handler calls `bridge.close_position()` for each position and reports partial failures.

Telegram MarkdownV2 formatting is escaped through `ui.prompts.escape_md_v2`. When adding a new view, keep all user-controlled symbols, reasons, and error messages escaped before interpolation.

## Terminal dashboard

The dashboard is intentionally lightweight and uses Rich rather than a GUI toolkit. Its header shows the configured paper/live mode and exchange and reads daily P&L through the shared `calculate_daily_pl(symbol)` bridge method. Its footer shows uptime, open-position count, and mode. Activity logs are in-memory and capped at 50 entries.

The dashboard is a display surface only. Start/stop controls in Telegram currently change controller state; they do not start or stop an autonomous scanner because no scanner loop is wired into `app_server.py` yet.

## Desktop tray

`ui/system_tray.py` is an optional Windows presence layer using `pystray` and Pillow. The current tray callbacks update local status, open Telegram, show a position count, and emit best-effort notifications. They are not a second execution engine. PyQt6 is a separate desktop panel and is not started by `app_server.py`.

## Planned next capability: scan and execution service

The next high-value addition is a single explicit orchestrator with these boundaries:

1. Fetch tick and candles for one symbol and configured timeframes.
2. Build a `MarketSnapshot` and optionally call researcher/trader LLM roles.
3. Apply `risk_manager.evaluate()` before any order call.
4. Require an explicit judge approval when the judge role is enabled.
5. In paper mode, record the proposed order without sending it to the bridge.
6. In live mode, call `send_market_order()` and persist the result.
7. Run break-even, trailing, and drift-cancellation maintenance separately from signal generation.
8. Publish alert messages only after an observed order/persistence result.

This should be implemented as a lifecycle-owned service with cancellation, bounded timeouts, per-symbol isolation, and a clear dry-run result. The Telegram “Start” button should control that service rather than only changing a UI boolean.

## Configuration source of truth

The dataclasses in `config/__init__.py` and `.env.example` are authoritative. Environment variables use the `vilona_` prefix. The older `KINGAI_` examples and `authorized_users`/`admin_users` names are obsolete and should not be reintroduced.
