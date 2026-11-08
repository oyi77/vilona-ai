from __future__ import annotations

import threading
import sys
from pathlib import Path

from config import get_config
from trading.bridge_ccxt import CCXTBridge
from trading.bridge_mt5 import MT5Bridge
from ui.telegram_controller import TelegramController
from ui.terminal_dashboard import TerminalDashboard
from ui.system_tray import SystemTrayApp

def main():
    cfg = get_config()
    
    # 1. Initialize Trading Bridge
    try:
        if cfg.exchange.name.lower() == 'mt5':
            bridge = MT5Bridge()
        else:
            bridge = CCXTBridge(cfg.exchange)
            
        if not bridge.connect():
            print("Critical: Bridge connection failed")
            return 1
    except Exception as e:
        print(f"Critical Error initializing bridge: {e}")
        return 1

    # 2. Initialize UI Layers
    # Telegram Bot (Async)
    tg_controller = TelegramController(bridge)
    
    # System Tray (Windows only)
    tray_app = None
    if sys.platform == 'win32':
        tray_app = SystemTrayApp(bridge, cfg, tg_controller)
        tray_app.start()

    # Terminal Dashboard (Blocking/Live)
    try:
        def run_tg():
            tg_controller.start()
        
        tg_thread = threading.Thread(target=run_tg, daemon=True)
        tg_thread.start()

        # Run Dashboard
        dash = TerminalDashboard(bridge, cfg)
        # Feed logs from bridge/engine to dashboard
        # (In a full impl, we'd use a queue or observer pattern)
        dash.start()
        
    except KeyboardInterrupt:
        print("Shutting down Vilona AI...")
    except Exception as e:
        print(f"Runtime Error: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
