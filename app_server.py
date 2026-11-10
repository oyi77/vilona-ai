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
from ui.system_tray import SystemTrayApp

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

    # 2. Initialize UI Layers
    tg_controller = TelegramController(bridge)

    tray_app = None
    if sys.platform == 'win32' and not cfg.headless:
        tray_app = SystemTrayApp(bridge, cfg, tg_controller)
        tray_app.start()

    # Terminal Dashboard & Telegram Threads
    def run_tg():
        try:
            tg_controller.start()
        except Exception as e:
            logger.error(f"Telegram Bot thread crashed: {e}")
            shutdown_event.set()

    tg_thread = threading.Thread(target=run_tg, daemon=True)
    tg_thread.start()

    dash = TerminalDashboard(bridge, cfg)

    def run_dash():
        try:
            dash.start()
        except Exception as e:
            logger.error(f"Dashboard thread crashed: {e}")
            shutdown_event.set()

    dash_thread = threading.Thread(target=run_dash, daemon=True)
    dash_thread.start()

    try:
        # Wait on shutdown_event or KeyboardInterrupt/signals
        while not shutdown_event.is_set():
            shutdown_event.wait(timeout=1.0)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutdown signal received")
        shutdown_event.set()
    finally:
        # Clean shutdown sequence
        logger.info("Initiating clean shutdown...")
        if hasattr(dash, 'stop'):
            try:
                dash.stop()
            except Exception as e:
                logger.error(f"Error stopping dashboard: {e}")

        if hasattr(tg_controller, 'stop'):
            try:
                tg_controller.stop()
            except Exception as e:
                logger.error(f"Error stopping Telegram: {e}")

        if bridge and hasattr(bridge, 'disconnect'):
            try:
                bridge.disconnect()
            except Exception as e:
                logger.error(f"Error disconnecting bridge: {e}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
