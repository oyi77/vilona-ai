from __future__ import annotations

import logging
import time
from typing import Optional

from telegram import Update, Bot
from telegram.ext import Application, ApplicationBuilder, CommandHandler, ContextTypes

from config import get_config
from trading.bridge_ccxt import CCXTBridge
from trading.trade_executor_v2 import calc_daily_pl

logger = logging.getLogger(__name__)


class TelegramController:
    def __init__(self, bridge: CCXTBridge):
        self.bridge = bridge
        self.config = get_config()
        self.telegram = self.config.telegram
        self.bot_token = self.telegram.bot_token
        self.running = False
        self._app: Optional[Application] = None
        self._stats = {
            'start_time': time.time(),
            'positions': [],
            'logs': [],
            'last_scan': 0,
            'paper_mode': True,
        }

    async def on_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        from ui.auth import is_authorized
        if not is_authorized(update.effective_chat.id):
            await update.message.reply_text("Unauthorized access")
            return
        await update.message.reply_text(
            "Vilona AI v2 started.\n"
            "/status - check positions\n"
            "/run - start scanner\n"
            "/stop - stop scanner\n"
            "/closeall - close all positions\n"
            "/balance - check balance\n"
            "/log - recent activity"
        )

    async def on_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        from ui.auth import is_authorized
        if not is_authorized(update.effective_chat.id):
            await update.message.reply_text("Unauthorized access")
            return
        positions = self.bridge.get_positions()
        pl, wins, total = calc_daily_pl(self.bridge, 'BTC/USDT')
        text = f"Positions: {len(positions)}\n"
        text += f"Daily P/L: {pl:.2f} USDT ({wins}/{total} closed)\n"
        for p in positions[:5]:
            text += f"  {p.ticket} {p.symbol} {p.type} vol={p.volume} P/L={p.profit:.2f}\n"
        await update.message.reply_text(text)

    async def on_balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        from ui.auth import is_authorized
        if not is_authorized(update.effective_chat.id):
            await update.message.reply_text("Unauthorized access")
            return
        try:
            balance = self.bridge.exchange.fetch_balance() if hasattr(self.bridge, 'exchange') else {}
            usdt = balance.get('USDT', {}) if isinstance(balance, dict) else {}
            text = f"USDT: {usdt.get('total', 0):.2f}"
            await update.message.reply_text(text)
        except Exception as e:
            await update.message.reply_text(f"Error: {e}")

    async def on_closeall(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        from ui.auth import is_admin
        if not is_admin(update.effective_chat.id):
            await update.message.reply_text("Admin-only command")
            return
        positions = self.bridge.get_positions()
        if not positions:
            await update.message.reply_text("No open positions.")
            return
        for p in positions:
            self.bridge.close_position(p.ticket, p.symbol)
        await update.message.reply_text(f"Closed {len(positions)} positions.")

    async def on_stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        from ui.auth import is_admin
        if not is_admin(update.effective_chat.id):
            await update.message.reply_text("Admin-only command")
            return
        self.running = False
        await update.message.reply_text("Scanner stopped.")

    async def on_start_scan(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        from ui.auth import is_admin
        if not is_admin(update.effective_chat.id):
            await update.message.reply_text("Admin-only command")
            return
        self.running = True
        await update.message.reply_text("Scanner restarted.")

    async def on_log(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        from ui.auth import is_admin
        if not is_admin(update.effective_chat.id):
            await update.message.reply_text("Admin-only command")
            return
        logs = self._stats['logs'][-20:]
        if not logs:
            await update.message.reply_text("No logs yet.")
            return
        await update.message.reply_text("\n".join(logs[-10:]))

    def register_commands(self, application: Application):
        application.add_handler(CommandHandler('start', self.on_start))
        application.add_handler(CommandHandler('status', self.on_status))
        application.add_handler(CommandHandler('balance', self.on_balance))
        application.add_handler(CommandHandler('closeall', self.on_closeall))
        application.add_handler(CommandHandler('stop', self.on_stop))
        application.add_handler(CommandHandler('run', self.on_start_scan))
        application.add_handler(CommandHandler('log', self.on_log))

    def start(self):
        if not self.bot_token:
            logger.warning("Telegram bot token not configured")
            return
        self.running = True
        app = ApplicationBuilder().token(self.bot_token).build()
        self.register_commands(app)
        app.run_polling()

    def send_message(self, chat_id: int, text: str):
        if not self.bot_token or chat_id == 0:
            return
        bot = Bot(token=self.bot_token)
        import asyncio
        try:
            asyncio.create_task(bot.send_message(chat_id=chat_id, text=text))
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
