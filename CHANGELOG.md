# Changelog

All notable changes are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Added

- **Multi-tenancy relay** — one service (`license_server.py`) now hosts both
  license validation and a central control plane. Desktop binaries connect
  **outbound only** (no inbound ports): handshake → poll commands → execute
  locally → report state changes. Telegram bot is the master-control UI driving
  each user's own desktop instance through the relay.
  - Tables: `devices`, `commands`, `events` (SQLite, same DB as licenses).
  - Device tokens stored as SHA-256 hashes, returned once at `/pair`.
  - Bot↔server auth via `X-Relay-Token` (`vilona_RELAY_BOT_TOKEN`, constant-time);
    device auth via Bearer token. Strict per-chat tenant scoping.
  - Command allowlist (no raw order exec in this slice): `status`, `balance`,
    `positions`, `runtime.start/stop/emergency_stop/emergency_reset`.
    `runtime.start` blocked for unlicensed devices (server + client).
  - Event reports allowlisted kinds, payload bounded to 64KB; leases expire and
    recover.
- **Desktop relay client** (`client/client.py`) — `RelayClient` polling loop with
  exponential backoff, injected command callback (never imports MT5/builds a
  second bridge), outbound-only. Wired into `app_server.py` as a daemon thread,
  started only when `vilona_RELAY_URL` + `vilona_RELAY_DEVICE_TOKEN` are set;
  stopped cleanly on shutdown. Non-fatal if relay is unreachable.
- **TGCloud bot commands** — `/pair <name>` (one-time token), `/devices`,
  `/license`, and `/status`/`/balance`/`/start_scan`/`/stop_scan`/`/emergency_stop`
  /`/emergency_reset` routed through the relay (async queue-and-report).
  `/setkeys` and `/setbackend` retired: exchange keys stay local on the desktop;
  no secrets accepted in chat.
- Tests: `tests/test_relay.py` (tenant isolation, token handling, command
  allowlist, licensing gate, payload bounds) and `tests/test_relay_client.py`
  (full phone-home roundtrip, unlicensed gate). Suite now 37 passing.

### Changed

- Self-hosted license server replaces the external vendor dependency; client
  points at `vilona_LICENSE_SERVER_URL`.

## [v2.3.0] — 2026-11-11

### Added

- **Serverless Telegram bot** (`tgcloud-bot/`) — Telegram Mini App bot running on
  Telegram's serverless platform (V8 isolate). Node.js project, deploys via
  `npx tgcloud push`. Handles registration, per-user exchange credentials,
  admin approval flow, and proxies `/status`/`/balance` to the Python backend.
  Bot: `@agent_1ai2_bot`.
- **Multi-user registration system** — SQLite-backed user registry
  (`ui/user_registry.py`) with admin approval workflow. First registrant
  auto-approved as admin.
- **Per-user exchange credentials** — stored in per-user DB row; exchanged at
  `/setkeys`; used when proxying trading commands to the Python backend.
- **LLM SSE streaming** — `llm/client.py` upgraded with SSE endpoint support;
  `llm/endpoints.py` added (OpenAI-compatible gateway streaming); tested E2E via
  Telethon on `@agent_1ai2_bot`.
- **KingAI parity port** — trading layer fully ported from KingAI:
  `trading/news_guard.py`, `trading/economic_calendar.py`,
  `trading/session_guard.py`, `trading/signal_gatekeeper.py`,
  `trading/trade_executor.py`, `trading/trade_history.py`,
  `trading/recorder.py`, `trading/performance.py`, `trading/token_stats.py`,
  `trading/account_mode.py`, `trading/settings.py`,
  `trading/strategy_validators.py`, `trading/distance_targets.py`,
  `trading/mt5_detect.py`, `data/king_signals.csv`.
- **LLM layer** — `llm/anthropic_adapter.py`, `llm/model_router.py`,
  `llm/budget.py`, `llm/reasoning.py`, `llm/ai_client.py`; SSE streaming via
  `llm/endpoints.py`.
- **Armada autonomous agents** — `armada/hub.py`, `armada/worker.py`,
  `armada/model.py`, `armada/governor.py`, `armada/protocol.py`.
- **Core infrastructure** — `core/account_license.py`, `core/license_client.py`,
  `core/secure_store.py`, `core/market_cache.py`, `core/usage_log.py`,
  `core/worker.py`, `core/qt.py`.
- **i18n** — `core/i18n.py`, `core/i18n_strings.py`, `core/i18n_armada.py`,
  `core/i18n_king.py`.
- **FastAPI trading backend** (`app_server.py`) — lightweight HTTP API on
  `:8300` exposing `/api/status` and `/api/balance`; started as a daemon thread
  when the Python backend boots. Used by the serverless Telegram bot as
  `OUTBOUND_URL`.
- **`core/config.py`** — supplementary config module.
- **tgcloud-bot docs** — `docs/tgcloud-sdk.md` (full SDK reference),
  `AGENTS.md` (project orientation for AI assistants).

### Changed

- **`app_server.py`** — simplified bridge start; FastAPI trading backend thread
  added; Telegram polling and dashboard remain conditional on config.
- **`core/runtime.py`** — `RuntimeSupervisor` wired with market data,
  LLM signal provider, and judge client.
- **`config/__init__.py`** — `market_type`, `paper_trading` defaults and
  validation; Docker build uses `requirements-core.txt`.
- **`ui/auth.py`** — multi-user aware; falls back to legacy config allowlist.
- **`ui/telegram_controller.py`** — extended with advanced runtime controls.
- **`llm/client.py`** — SSE streaming support for OpenAI-compatible gateways.

### Fixed

- Headless paper boot premature exit when UI components unconfigured.
- Config/Dockerfile corrupted by `@ours` merge placeholder (restored).
- Headless boot subprocess on Windows: `SystemRoot` and `TEMP` passed to
  Nuitka-built executable subprocess.
- `core/runtime.py` bridge connection check for lazy constant maps.

### Tests

- `pytest tests/` → 29/29 passing.
- `test_headless_boot.py` updated for Windows subprocess env passthrough.
