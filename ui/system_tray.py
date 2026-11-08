from __future__ import annotations

import logging
import threading
from typing import Any, Optional
from pathlib import Path

import pystray
from pystray import MenuItem as Item, Menu
from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)


class SystemTrayApp:
    def __init__(self, bridge: Any, config: Any, telegram_controller: Any = None):
        self.bridge = bridge
        self.config = config
        self.telegram = telegram_controller
        self._icon: Optional[pystray.Icon] = None
        self._running = False
        self._status = "Stopped"

    def _create_icon_image(self) -> Image:
        # Create a simple 32x32 icon programmatically
        size = 32
        image = Image.new('RGB', (size, size), '#1a1a2e')
        draw = ImageDraw.Draw(image)
        
        # Draw a simple robot face
        draw.ellipse([4, 4, 28, 28], fill='#16213e', outline='#0f3460')
        draw.ellipse([10, 10, 14, 14], fill='#00d9ff')  # Left eye
        draw.ellipse([18, 10, 22, 14], fill='#00d9ff')  # Right eye
        draw.arc([8, 18, 24, 24], 0, 180, fill='#00d9ff', width=2)  # Smile
        
        return image

    def _build_menu(self) -> Menu:
        return Menu(
            Item(f"Status: {self._status}", lambda: None, enabled=False),
            Item("─" * 20, lambda: None, enabled=False),
            Item("▶️ Start Scanner", self._on_start),
            Item("⏹️ Stop Scanner", self._on_stop),
            Item("🔄 Restart", self._on_restart),
            Item("─" * 20, lambda: None, enabled=False),
            Item("📱 Open Telegram Bot", self._on_open_telegram),
            Item("📊 View Status", self._on_view_status),
            Item("─" * 20, lambda: None, enabled=False),
            Item("❌ Exit", self._on_exit),
        )

    def _on_start(self, icon: pystray.Icon, item: Item):
        self._status = "Running"
        icon.title = "Vilona AI v2 - Running"
        self._notify("Scanner Started", "Vilona AI is now scanning for trades.")
        logger.info("Scanner started via system tray")

    def _on_stop(self, icon: pystray.Icon, item: Item):
        self._status = "Stopped"
        icon.title = "Vilona AI v2 - Stopped"
        self._notify("Scanner Stopped", "Vilona AI has stopped scanning.")
        logger.info("Scanner stopped via system tray")

    def _on_restart(self, icon: pystray.Icon, item: Item):
        self._on_stop(icon, item)
        self._on_start(icon, item)
        logger.info("Scanner restarted via system tray")

    def _on_open_telegram(self, icon: pystray.Icon, item: Item):
        import webbrowser
        bot_username = self.config.telegram.bot_token.split(':')[0] if self.config.telegram.bot_token else "bot"
        webbrowser.open(f"https://t.me/{bot_username}")
        logger.info("Opened Telegram bot in browser")

    def _on_view_status(self, icon: pystray.Icon, item: Item):
        try:
            positions = self.bridge.get_positions() if hasattr(self.bridge, 'get_positions') else []
            self._notify("Trading Status", f"Open Positions: {len(positions)}")
        except Exception as e:
            self._notify("Status Error", str(e))

    def _on_exit(self, icon: pystray.Icon, item: Item):
        self._running = False
        icon.stop()
        logger.info("Exiting via system tray")

    def _notify(self, title: str, message: str):
        """Send native Windows notification."""
        try:
            from win10toast import ToastNotifier
            toaster = ToastNotifier()
            toaster.show_toast(title, message, duration=5, icon_path=None)
        except ImportError:
            logger.debug("win10toast not available, skipping native notification")
        except Exception as e:
            logger.debug(f"Notification failed: {e}")

    def start(self):
        self._running = True
        icon = pystray.Icon("vilona_ai", self._create_icon_image(), "Vilona AI v2", self._build_menu())
        self._icon = icon
        icon.run_detached()
        logger.info("System tray icon started")

    def stop(self):
        if self._icon:
            self._icon.stop()
        self._running = False
