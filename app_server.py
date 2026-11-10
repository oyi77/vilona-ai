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

        if not bridge.connect():
            logger.error("Critical: Bridge connection failed")
            return 1
    except Exception as e:
        logger.error(f"Critical Error initializing bridge: {e}")
        return 1

    # 2. Initialize UI Layers
    tg_controller = TelegramController(bridge)

    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)
    # Headless/paper mode: UI failures are non-fatal. Only set shutdown_event
    # if a UI thread actually started and then crashed unexpectedly.
    # A UI skipped due to missing config must not kill the process.
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

    tray_app = None
    if sys.platform == 'win32' and not cfg.headless:
        tray_app = SystemTrayApp(bridge, cfg, tg_controller)
        tray_app.start()

    dash = TerminalDashboard(bridge, cfg)

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

        if bridge and hasattr(bridge, 'disconnect'):
            try:
                bridge.disconnect()
            except Exception as e:
                logger.error(f"Error disconnecting bridge: {e}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
