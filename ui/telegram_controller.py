# Telegram UX layer for Vilona AI v2 - Rich Command Center
from __future__ import annotations

import logging
import time
from typing import Optional, Any

from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters
from telegram.constants import ParseMode

from config import get_config
from trading.trade_executor_v2 import calc_daily_pl
from ui.prompts import escape_md_v2
from ui.auth import is_authorized, is_admin

logger = logging.getLogger(__name__)


class TelegramController:
    def __init__(self, bridge: Any):
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
            'paper_mode': getattr(self.config.trading, 'paper_mode', True),
            'scanner_active': False,
        }

        # Persistent main menu
        self.main_menu = ReplyKeyboardMarkup(
            [
                [KeyboardButton("📊 Status"), KeyboardButton("💰 Balance")],
                [KeyboardButton("⚙️ Control"), KeyboardButton("📜 Logs")],
            ],
            resize_keyboard=True,
            one_time_keyboard=False,
        )

    def _fmt_price(self, val: float) -> str:
        return f"{val:.5f}"

    def _profit_icon(self, profit: float) -> str:
        if profit > 0:
            return "🟢"
        elif profit < 0:
            return "🔴"
        return "⚪"

    async def on_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not is_authorized(update.effective_chat.id):
            await update.message.reply_text("⚠️ Unauthorized access")
            return

        text = (
            f"🤖 *Vilona AI v2* is online\\.\n\n"
            f"Welcome back\\! Use the menu below to navigate:\n"
            f"• *Status* \\- Open positions \\& P/L\n"
            f"• *Balance* \\- Account equity\n"
            f"• *Control* \\- Start/Stop scanner\n"
            f"• *Logs* \\- Recent activity\n\n"
            f"_Env_: `{escape_md_v2(self.config.exchange.name.upper())}` \\| "
            f"_Mode_: `{escape_md_v2('PAPER' if self._stats['paper_mode'] else 'LIVE')}`"
        )
        await update.message.reply_markdown_v2(text, reply_markup=self.main_menu)

    async def on_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not is_authorized(update.effective_chat.id):
            return

        text = update.message.text
        if text == "📊 Status":
            await self.send_status(update, context)
        elif text == "💰 Balance":
            await self.send_balance(update, context)
        elif text == "⚙️ Control":
            await self.send_control(update, context)
        elif text == "📜 Logs":
            await self.send_logs(update, context)
        else:
            await update.message.reply_text("Use buttons or commands.", reply_markup=self.main_menu)

    async def send_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        msg = update.message or update.callback_query.message
        chat_id = update.effective_chat.id

        if not is_authorized(chat_id):
            await msg.reply_text("⚠️ Unauthorized", reply_markup=self.main_menu)
            return

        positions = self.bridge.get_positions()
        pl, wins, total = calc_daily_pl(self.bridge, 'BTC/USDT')

        buttons = []
        if positions:
            buttons.append([InlineKeyboardButton("🔴 Close All", callback_data="close_all")])
        buttons.append([InlineKeyboardButton("🔄 Refresh", callback_data="refresh_status")])
        kb = InlineKeyboardMarkup(buttons)

        pnl_str = f"{pl:.2f}"
        pnl_ico = self._profit_icon(pl)
        text = (
            f"*📊 Trading Status*\n\n"
            f"*Positions Open:* `{len(positions)}`\n"
            f"*Daily P/L:* `{pnl_str}` USDT {pnl_ico}\n"
            f"*Win Rate:* `{wins}/{total}`\n\n"
        )
        if positions:
            text += "*Open Trades:*\n"
            for p in positions[:10]:
                ico = "📈" if str(p.type).upper() in ["BUY", "BUY_STOP"] else "📉"
                text += (
                    f"• `{p.ticket}` {ico} *{escape_md_v2(p.symbol)}* \n"
                    f"  `{self._fmt_price(p.price_open)}` \\| `{p.volume}` lot \\| "
                    f"P/L: `{p.profit:.2f}` {self._profit_icon(p.profit)}\n"
                    f"  SL: `{self._fmt_price(p.sl)}` \\| TP: `{self._fmt_price(p.tp)}`\n"
                )
        else:
            text += "_No open positions._\n"

        await msg.reply_markdown_v2(text, reply_markup=kb)

    async def send_balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        msg = update.message or update.callback_query.message
        chat_id = update.effective_chat.id

        if not is_authorized(chat_id):
            await msg.reply_text("⚠️ Unauthorized", reply_markup=self.main_menu)
            return

        if hasattr(self.bridge, 'exchange') and hasattr(self.bridge, 'fetch_balance'):
            try:
                balance = self.bridge.exchange.fetch_balance() if hasattr(self.bridge, 'exchange') else {}
                if isinstance(balance, dict):
                    usdt = balance.get('USDT', {})
                    total = usdt.get('total', 0)
                    free = usdt.get('free', 0)
                else:
                    total = 0
                    free = 0
                text = (
                    f"*💰 Account Balance*\n\n"
                    f"*USDT Total:* `{total:.2f}`\n"
                    f"*USDT Free:* `{free:.2f}`\n"
                )
            except Exception as e:
                text = f"*❌ Error Fetching Balance*\n\n`{escape_md_v2(str(e))}`"
            await msg.reply_markdown_v2(text, reply_markup=self.main_menu)
        else:
            try:
                balance_info = self.bridge.account_info() if hasattr(self.bridge, 'account_info') else {}
                acc = balance_info[0] if isinstance(balance_info, (tuple, list)) else None
                text = (
                    f"*💰 Account Balance*\n\n"
                    f"*Balance:* `{acc.balance:.2f}`\n"
                    f"*Equity:* `{acc.equity:.2f}`\n"
                    f"*Margin:* `{acc.margin:.2f}`\n"
                    f"*Free Margin:* `{acc.margin_free:.2f}`\n"
                )
            except Exception as e:
                text = f"*❌ Error Fetching Balance*\n\n`{escape_md_v2(str(e))}`"
            await msg.reply_markdown_v2(text, reply_markup=self.main_menu)

    async def send_control(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        msg = update.message or update.callback_query.message
        chat_id = update.effective_chat.id

        if not is_authorized(chat_id):
            await msg.reply_text("⚠️ Unauthorized", reply_markup=self.main_menu)
            return

        status = "🟢 Running" if self._stats['scanner_active'] else "🔴 Stopped"
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("▶️ Start", callback_data="start_scan"),
                InlineKeyboardButton("⏹️ Stop", callback_data="stop_scan")
            ],
            [InlineKeyboardButton("🔄 Restart", callback_data="restart_scan")]
        ])
        text = (
            f"*⚙️ Scanner Control*\n\n"
            f"*State:* {status}\n"
            f"_Mode_: `{escape_md_v2('PAPER' if self._stats['paper_mode'] else 'LIVE')}`\n"
            f"_Exchange_: `{escape_md_v2(self.config.exchange.name.upper())}`"
        )
        await msg.reply_markdown_v2(text, reply_markup=kb)

    async def send_logs(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        msg = update.message or update.callback_query.message
        chat_id = update.effective_chat.id

        if not is_authorized(chat_id):
            await msg.reply_text("⚠️ Unauthorized", reply_markup=self.main_menu)
            return

        logs = self._stats['logs'][-20:]
        if not logs:
            await msg.reply_text("No logs yet.", reply_markup=self.main_menu)
            return

        text = "*📜 Recent Logs*\n\n" + "\n".join(f"`{escape_md_v2(str(l))}`" for l in logs[-15:])
        await msg.reply_markdown_v2(text, reply_markup=self.main_menu)

    async def _cb_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        chat_id = query.message.chat_id
        if not is_authorized(chat_id):
            await query.answer("Unauthorized", show_alert=True)
            return

        if query.data == "refresh_status":
            await self.send_status(update, context)
        elif query.data == "close_all":
            await self.execute_close_all(update, context)
        elif query.data in ["start_scan", "stop_scan", "restart_scan"]:
            await self.execute_control(update, context, query.data)

    async def execute_close_all(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if not is_admin(update.effective_chat.id):
            await query.answer("Admin only", show_alert=True)
            return

        positions = self.bridge.get_positions()
        if not positions:
            await query.answer("No positions to close.", show_alert=True)
            return

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Yes, close all", callback_data="confirm_close_all"),
             InlineKeyboardButton("Cancel", callback_data="cancel_close")]
        ])
        await query.message.reply_markdown_v2(f"*⚠️ Are you sure you want to close {len(positions)} positions?*", reply_markup=kb)

    async def execute_control(self, update: Update, context: ContextTypes.DEFAULT_TYPE, cmd: str):
        query = update.callback_query
        if not is_admin(update.effective_chat.id):
            await query.answer("Admin only", show_alert=True)
            return

        if cmd == "start_scan":
            self._stats['scanner_active'] = True
            await query.message.reply_text("▶️ Scanner started.")
        elif cmd == "stop_scan":
            self._stats['scanner_active'] = False
            await query.message.reply_text("⏹️ Scanner stopped.")
        elif cmd == "restart_scan":
            self._stats['scanner_active'] = False
            await context.bot.send_message(query.message.chat_id, "🔄 Restarting...")
            self._stats['scanner_active'] = True
            await context.bot.send_message(query.message.chat_id, "▶️ Scanner restarted.")

    async def send_trade_alert(self, symbol: str, action: str, volume: float, price: float, sl: float, tp: float, ai_reason: str):
        if not self.bot_token:
            return
        chat_ids = self.telegram.chat_ids or []
        bot = Bot(token=self.bot_token)
        text = (
            f"*🚨 New Trade Alert*\n\n"
            f"`{escape_md_v2(symbol)}` {escape_md_v2(action)}\n"
            f"*Volume*: `{volume}` | *Price*: `{self._fmt_price(price)}`\n"
            f"*SL*: `{self._fmt_price(sl)}` | *TP*: `{self._fmt_price(tp)}`\n\n"
            f"*AI Logic:*\n_{escape_md_v2(ai_reason)}_"
        )
        for chat_id in chat_ids:
            try:
                await bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.MARKDOWN_V2)
            except Exception as e:
                logger.error(f"Alert failed to {chat_id}: {e}")

    def register_commands(self, application: Application):
        application.add_handler(CommandHandler('start', self.on_start))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.on_text))
        application.add_handler(CallbackQueryHandler(self._cb_query))

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
