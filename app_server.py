from __future__ import annotations

import threading
import logging
from logging.handlers import RotatingFileHandler
import sys
import signal
from pathlib import Path

from config import get_config
from trading.bridge_ccxt import CCXTBridge
from trading.bridge_mt5 import MT5Bridge
from ui.telegram_controller import TelegramController
from ui.terminal_dashboard import TerminalDashboard
# pystray/PIL not available on headless Linux — guard so Linux onefile doesn't crash
try:
    from ui.system_tray import SystemTrayApp
except ImportError:
    SystemTrayApp = None

from core.runtime import RuntimeSupervisor
from core.state_db import StateDB
from llm.client import get_llm_client
from core.runtime import LLMTradingProvider

logger = logging.getLogger('vilona-ai')

# Setup structured logging: RotatingFileHandler (10MB, 5 backups) + StreamHandler (console)
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)
log_file = log_dir / "vilona.log"

formatter = logging.Formatter(
    fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# Avoid duplicate handlers on re-import
if not logger.handlers:
    logger.setLevel(logging.INFO)
    file_handler = RotatingFileHandler(
        log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

shutdown_event = threading.Event()

def _signal_handler(signum, frame):
    logger.info(f"Signal {signum} received - shutting down")
    shutdown_event.set()

def main():
    cfg = get_config()

    # Validate config
    errors = cfg.validate()
    if errors:
        for err in errors:
            logger.error(f"Config validation error: {err}")
        return 1

    # 1. Initialize Trading Bridge
    bridge = None
    try:
        if cfg.exchange.name.lower() == 'mt5':
            bridge = MT5Bridge()
        else:
            bridge = CCXTBridge(cfg.exchange)

        connected = bridge.connect()
        # MT5 returns (success, message), while CCXT returns bool.
        if isinstance(connected, tuple):
            connected, message = connected
            if message:
                logger.info(message)
        if not connected:
            logger.error("Critical: Bridge connection failed")
            return 1
    except Exception as e:
        logger.error(f"Critical Error initializing bridge: {e}")
        return 1

    # 2. Start a lightweight HTTP API for Telegram Serverless handlers
    #    (serverless bot → this Python backend for trading data)
    from threading import Thread
    from fastapi import FastAPI, HTTPException
    import uvicorn as _uvicorn

    api_app = FastAPI(title="Vilona AI Trading Backend")

    @api_app.get("/api/status")
    def api_status(chat_id: int):
        runtime_status = runtime.status() if runtime else {}
        positions = []
        try:
            positions = [p for p in bridge.get_positions()][:10]
        except Exception:
            pass
        return {
            "runtime_state": runtime_status.get("state", "idle"),
            "paper": runtime_status.get("paper", cfg.paper_trading),
            "positions": [
                {"ticket": p.ticket, "symbol": p.symbol, "type": str(p.type)}
                for p in positions
            ],
            "symbols": cfg.trading.symbols,
        }

    @api_app.get("/api/balance")
    def api_balance(chat_id: int):
        try:
            bal = bridge.get_balance()
            return {"total": round(bal.get("total", bal.get("equity", 0.0)), 2),
                    "free": round(bal.get("free", 0.0), 2)}
        except Exception as e:
            raise HTTPException(status_code=502, detail=str(e))

    def _run_api():
        try:
            _uvicorn.run(api_app, host="127.0.0.1", port=8300, log_level="warning")
        except Exception as e:
            logger.error(f"API server crashed: {e}")

    Thread(target=_run_api, daemon=True, name="api-server").start()

    # 2. Initialize UI Layers
    signal_provider = None
    judge_client = None
    if cfg.llm.api_key:
        llm_client = get_llm_client()
        signal_provider = LLMTradingProvider(llm_client)
        if "judge" in cfg.enabled_personas:
            judge_client = llm_client
    runtime = RuntimeSupervisor(bridge, cfg, state_db=StateDB(), signal_provider=signal_provider, judge_client=judge_client)
    tg_controller = TelegramController(bridge, runtime=runtime)
    if cfg.autonomy_enabled:
        runtime.start()

    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)
    # Headless/paper mode: UI failures are non-fatal. Only set shutdown_event
    # if a UI thread actually started and then crashed unexpectedly.
    # A UI skipped due to missing config must not kill the process.

    tray_app = None
    if sys.platform == 'win32' and not cfg.headless and SystemTrayApp is not None:
        tray_app = SystemTrayApp(bridge, cfg, tg_controller)
        tray_app.start()

    tg_thread = None
    if cfg.telegram.bot_token:
        def run_tg():
            try:
                tg_controller.start()
            except Exception as e:
                logger.error(f"Telegram Bot thread crashed: {e}")
                shutdown_event.set()

        tg_thread = threading.Thread(target=run_tg, daemon=True)
        tg_thread.start()
    else:
        logger.info("Telegram bot token not configured — skipping Telegram thread")

    dash = TerminalDashboard(bridge, cfg, runtime=runtime)

    dash_thread = None
    if sys.stdout.isatty() and not cfg.headless:
        def run_dash():
            try:
                dash.start()
            except Exception as e:
                logger.error(f"Dashboard thread crashed: {e}")
                shutdown_event.set()

        dash_thread = threading.Thread(target=run_dash, daemon=True)
        dash_thread.start()
    else:
        logger.info("Terminal dashboard: non-TTY or headless — skipping dashboard thread")

    # Main loop — idle heartbeat every 60s when nothing to do
    heartbeat_counter = 0
    try:
        while not shutdown_event.is_set():
            shutdown_event.wait(timeout=1.0)
            heartbeat_counter += 1
            if heartbeat_counter >= 60:
                heartbeat_counter = 0
                logger.info("Heartbeat: process alive, waiting for shutdown...")
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutdown signal received")
        shutdown_event.set()
    finally:
        # Clean shutdown sequence
        logger.info("Initiating clean shutdown...")
        if dash_thread and dash.running:
            try:
                dash.stop()
            except Exception as e:
                logger.error(f"Error stopping dashboard: {e}")

        if tg_thread and tg_controller.running:
            try:
                tg_controller.stop()
            except Exception as e:
                logger.error(f"Error stopping Telegram: {e}")

        try:
            runtime.stop()
        except Exception as e:
            logger.error(f"Error stopping runtime: {e}")

        if bridge and hasattr(bridge, 'disconnect'):
            try:
                bridge.disconnect()
            except Exception as e:
                logger.error(f"Error disconnecting bridge: {e}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())