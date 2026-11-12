# Telegram UX layer for Vilona AI v2 - Rich Command Center
from __future__ import annotations

import asyncio
import logging
import threading
import time
import uuid
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
    def __init__(self, bridge: Any, runtime: Any = None):
        self.bridge = bridge
        self.runtime = runtime
        self.config = get_config()
        self.telegram = self.config.telegram
        self.bot_token = self.telegram.bot_token
        self.running = False
        self._app: Optional[Application] = None
        self._pending_confirmations: dict[str, dict[str, Any]] = {}
        self._confirmation_lock = threading.Lock()
        self.confirmation_ttl_seconds = 30
        self._stats = {
            'start_time': time.time(),
            'positions': [],
            'logs': [],
            'last_scan': 0,
            'paper_mode': self.config.paper_trading,
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
        from ui.auth import get_registry
        chat_id = update.effective_chat.id
        user = update.effective_user
        registry = get_registry()
        session = registry.get(chat_id)

        if session is None:
            # New user — register (pending approval unless first)
            session = registry.register(
                chat_id=chat_id,
                username=getattr(user, 'username', '') or '',
                first_name=getattr(user, 'first_name', '') or '',
            )
            if session.approved and session.is_admin:
                await update.message.reply_text(
                    "🤖 *Vilona AI v2* first-time setup complete\\.\n\n"
                    "You are registered as *admin* — approve other users with "
                    "/approve `<chat_id>`\\.\n\n"
                    "Use the menu below to navigate\\.",
                    parse_mode=ParseMode.MARKDOWN_V2,
                    reply_markup=self.main_menu,
                )
                return
            await update.message.reply_text(
                "🤖 *Vilona AI v2*\n\n"
                "Registration received\\.\n\n"
                "⚠️ *Pending approval* — an admin must approve your access "
                "before you can use the bot\\.\n"
                f"Your chat ID: `{chat_id}`\n\n"
                "Try /start again after approval\\.",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            return

        if not session.approved:
            await update.message.reply_text(
                "⚠️ *Pending approval*\n\n"
                "Your registration is awaiting admin approval\\.\n"
                f"Your chat ID: `{chat_id}`",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            return

        text = (
            f"🤖 *Vilona AI v2* is online\\.\n\n"
            f"Welcome back{(', ' + escape_md_v2(session.first_name)) if session.first_name else ''}\\! "
            f"Use the menu below to navigate:\n"
            f"• *Status* \\- Open positions \\& P/L\n"
            f"• *Balance* \\- Account equity\n"
            f"• *Control* \\- Start/Stop scanner\n"
            f"• *Logs* \\- Recent activity\n\n"
            f"_Env_: `{escape_md_v2(session.exchange_name.upper())}` \\| "
            f"_Mode_: `{escape_md_v2('PAPER' if self._stats['paper_mode'] else 'LIVE')}`"
        )
        await update.message.reply_markdown_v2(text, reply_markup=self.main_menu)
    async def on_approve(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        from ui.auth import is_admin, get_registry
        registry = get_registry()
        if not is_admin(update.effective_chat.id):
            await update.message.reply_text("Admin only")
            return
        if not context.args:
            pending = registry.list_pending()
            if not pending:
                await update.message.reply_text("No pending registrations.")
                return
            lines = ["Pending registrations:"] + [
                f"• `{u.chat_id}` — {u.username or u.first_name}" for u in pending
            ]
            await update.message.reply_text("\n".join(lines))
            return
        try:
            target = int(context.args[0])
        except ValueError:
            await update.message.reply_text("Usage: /approve <chat_id>")
            return
        await update.message.reply_text(
            f"Approved `{target}`." if registry.approve(target)
            else f"`{target}` not found."
        )

    async def on_decline(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        from ui.auth import is_admin, get_registry
        if not is_admin(update.effective_chat.id):
            await update.message.reply_text("Admin only")
            return
        if not context.args:
            await update.message.reply_text("Usage: /decline <chat_id> (removes registration)")
            return
        try:
            target = int(context.args[0])
        except ValueError:
            await update.message.reply_text("Usage: /decline <chat_id>")
            return
        from ui.auth import get_registry
        removed = get_registry().remove(target)
        await update.message.reply_text(f"Removed `{target}`." if removed else f"`{target}` not found.")

    async def on_users(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        from ui.auth import is_admin, get_registry
        if not is_admin(update.effective_chat.id):
            await update.message.reply_text("Admin only")
            return
        users = get_registry().list_all()
        if not users:
            await update.message.reply_text("No registered users.")
            return
        lines = ["Registered users:"]
        for u in users:
            status = "admin" if u.is_admin else ("active" if u.approved else "pending")
            lines.append(f"• `{u.chat_id}` — {u.username or u.first_name} [{status}]")
        await update.message.reply_text("\n".join(lines))

    async def on_setkeys(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Persist per-user exchange credentials: /setkeys <exchange> <api_key> <api_secret>"""
        from ui.auth import get_registry, get_session
        chat_id = update.effective_chat.id
        session = get_session(chat_id)
        if session is None or not session.approved:
            await update.message.reply_text("Register and get approved first (/start).")
            return
        if not context.args or len(context.args) < 3:
            await update.message.reply_text(
                "Usage: /setkeys <exchange> <api_key> <api_secret>\n"
                "e.g. /setkeys binance YOUR_KEY YOUR_SECRET"
            )
            return
        exchange, key, secret = context.args[0], context.args[1], context.args[2]
        registry = get_registry()
        with registry._lock:
            import sqlite3 as _sq
            conn = registry._connect()
            try:
                conn.execute(
                    "UPDATE tg_users SET exchange_name=?, exchange_api_key=?, exchange_api_secret=? WHERE chat_id=?",
                    (exchange, key, secret, chat_id),
                )
                conn.commit()
            finally:
                conn.close()
        session.exchange_name = exchange
        session.exchange_api_key = key
        session.exchange_api_secret = secret
        session.bridge = None  # rebuild lazily on next use
        await update.message.reply_text(
            f"Credentials saved for `{exchange}`. Your next /balance or /status "
            f"uses your own account."
        )

    def _user_bridge(self, chat_id: int):
        """Per-user CCXT bridge (lazy), falling back to shared bridge when
        the user hasn't set their own credentials."""
        from ui.auth import get_session
        session = get_session(chat_id)
        if session is None or not session.approved:
            return self.bridge
        if session.bridge is not None:
            return session.bridge
        if session.exchange_api_key and session.exchange_api_secret:
            try:
                from dataclasses import replace as _replace
                from config import get_config
                base = get_config().exchange
                user_cfg = _replace(
                    base,
                    name=session.exchange_name,
                    api_key=session.exchange_api_key,
                    api_secret=session.exchange_api_secret,
                    sandbox=session.exchange_sandbox,
                )
                from trading.bridge_ccxt import CCXTBridge
                bridge = CCXTBridge(user_cfg)
                if bridge.connect():
                    session.bridge = bridge
                    logger.info("Built per-user bridge for chat %s (%s)", chat_id, session.exchange_name)
                    return bridge
            except Exception as e:
                logger.error("Per-user bridge failed for %s: %s", chat_id, e)
        return self.bridge

    async def on_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not is_authorized(update.effective_chat.id):
            await update.message.reply_text("Unauthorized access")
            return
        text = (
            "Vilona AI commands:\n\n"
            "/start — register / login\n"
            "/status — positions and daily P/L (your account)\n"
            "/health — runtime, bridge, database, and error state\n"
            "/events [count] — recent persisted runtime events\n"
            "/balance — account balance (your account)\n"
            "/setkeys <exchange> <key> <secret> — connect your own exchange\n"
            "/control — interactive runtime controls\n"
            "/start_scan, /stop_scan, /restart_scan — admin controls\n"
            "/emergency_stop [reason] — immediately halt the supervisor\n"
            "/emergency_reset — admin confirmation required\n"
            "/users — list registered users (admin)\n"
            "/approve <chat_id> — approve pending registration (admin)\n"
            "/decline <chat_id> — remove a registration (admin)\n"
            "/logs — recent controller logs"
        )
        await update.message.reply_text(text, reply_markup=self.main_menu)

    async def on_health_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self.send_health(update, context)

    async def on_events_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        count = 10
        if context.args:
            try:
                count = max(1, min(int(context.args[0]), 30))
            except (TypeError, ValueError):
                await update.message.reply_text("Usage: /events [1-30]")
                return
        await self.send_events(update, context, count)

    async def on_emergency_stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not is_admin(update.effective_chat.id):
            await update.message.reply_text("Admin only")
            return
        reason = " ".join(context.args).strip() if context.args else "emergency stop requested from Telegram"
        if self.runtime:
            self.runtime.emergency_stop(reason)
            await update.message.reply_text(f"EMERGENCY STOP engaged. Reason: {reason}")
        else:
            await update.message.reply_text("Runtime supervisor is unavailable.")

    async def on_emergency_reset(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not is_admin(update.effective_chat.id):
            await update.message.reply_text("Admin only")
            return
        token = self._create_confirmation(update.effective_chat.id, "emergency_reset")
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Confirm reset", callback_data=f"confirm:emergency_reset:{token}"),
             InlineKeyboardButton("Cancel", callback_data=f"cancel:{token}")]
        ])
        await update.message.reply_text(
            "Reset emergency stop? This only clears the supervisor latch; it does not start scanning.",
            reply_markup=kb,
        )

    async def on_start_scan_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self._command_control(update, "start_scan")

    async def on_stop_scan_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self._command_control(update, "stop_scan")

    async def on_restart_scan_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self._command_control(update, "restart_scan")

    async def _command_control(self, update: Update, action: str):
        if not is_admin(update.effective_chat.id):
            await update.message.reply_text("Admin only")
            return
        result = self._apply_control(action)
        await update.message.reply_text(result)

    def _apply_control(self, action: str) -> str:
        if not self.runtime:
            return "Runtime supervisor is unavailable."
        if action == "start_scan":
            return "Scanner started." if self.runtime.start() else "Scanner was not started (already running or emergency-stopped)."
        if action == "stop_scan":
            return "Scanner stopped." if self.runtime.stop() else "Scanner is still stopping."
        if action == "restart_scan":
            self.runtime.stop()
            return "Scanner restarted." if self.runtime.start() else "Scanner restart blocked (check emergency-stop state)."
        return "Unknown control action."

    def _create_confirmation(self, chat_id: int, action: str, payload: Optional[dict[str, Any]] = None) -> str:
        token = uuid.uuid4().hex[:12]
        with self._confirmation_lock:
            self._pending_confirmations[token] = {
                "chat_id": chat_id,
                "action": action,
                "payload": payload or {},
                "expires_at": time.time() + self.confirmation_ttl_seconds,
            }
        return token

    def _consume_confirmation(self, token: str, chat_id: int, action: str) -> Optional[dict[str, Any]]:
        with self._confirmation_lock:
            pending = self._pending_confirmations.get(token)
            if not pending or pending["chat_id"] != chat_id or pending["action"] != action:
                return None
            if pending["expires_at"] < time.time():
                self._pending_confirmations.pop(token, None)
                return None
            self._pending_confirmations.pop(token, None)
            return pending["payload"]

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

        bridge = self._user_bridge(chat_id)
        positions = bridge.get_positions()
        symbol = self.config.trading.symbols[0]
        pl, wins, total = calc_daily_pl(bridge, symbol)

        buttons = []
        if positions:
            buttons.append([InlineKeyboardButton("🔴 Close All", callback_data="close_all")])
        buttons.append([InlineKeyboardButton("🔄 Refresh", callback_data="refresh_status")])
        kb = InlineKeyboardMarkup(buttons)

        pnl_str = f"{pl:.2f}"
        pnl_ico = self._profit_icon(pl)
        runtime_state = (self.runtime.status().get("state", "ui-only") if self.runtime else "ui-only")
        guard_lines = ""
        if getattr(self.config.trading, 'news_guard_enabled', False):
            try:
                from trading.news_guard import get_zone_status
                ns = get_zone_status(None, 30, 5)
                guard_lines += f"\\*News Guard:\\* `{escape_md_v2(ns.zone)}`\n"
            except Exception:
                guard_lines += "\\*News Guard:\\* `unavailable`\n"
        try:
            from llm import budget as llm_budget
            over,_a,used,limit = llm_budget.check('autotrade')
            if limit > 0:
                guard_lines += f"\\*LLM Budget:\\* `{used}/{limit}` {'⚠️ EXCEEDED' if over else 'ok'}\n"
        except Exception:
            pass
        text = (
            f"*📊 Trading Status*\n\n"
            f"*Runtime:* `{escape_md_v2(runtime_state)}`\n"
            f"*Positions Open:* `{len(positions)}`\n"
            f"*Daily P/L:* `{pnl_str}` USDT {pnl_ico}\n"
            f"*Win Rate:* `{wins}/{total}`\n"
            f"{guard_lines}\n"
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

        bridge = self._user_bridge(chat_id)
        if hasattr(bridge, 'get_balance'):
            try:
                balance = bridge.get_balance()
                total = balance.get('total', 0.0)
                free = balance.get('free', 0.0)
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
                balance = bridge.get_balance()
                text = (
                    f"*💰 Account Balance*\n\n"
                    f"*Balance:* `{balance.get('balance', 0.0):.2f}`\n"
                    f"*Equity:* `{balance.get('equity', 0.0):.2f}`\n"
                    f"*Margin:* `{balance.get('margin', 0.0):.2f}`\n"
                    f"*Free Margin:* `{balance.get('free_margin', 0.0):.2f}`\n"
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

        runtime_status = self.runtime.status() if self.runtime else {}
        active = runtime_status.get('state') == 'running' if runtime_status else self._stats['scanner_active']
        status = "🟢 Running" if active else "🔴 Stopped"
        start_token = self._create_confirmation(chat_id, "control:start_scan")
        stop_token = self._create_confirmation(chat_id, "control:stop_scan")
        restart_token = self._create_confirmation(chat_id, "control:restart_scan")
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("▶️ Start", callback_data=f"control:start_scan:{start_token}"),
                InlineKeyboardButton("⏹️ Stop", callback_data=f"control:stop_scan:{stop_token}")
            ],
            [InlineKeyboardButton("🔄 Restart", callback_data=f"control:restart_scan:{restart_token}")]
        ])
        text = (
            f"*⚙️ Scanner Control*\n\n"
            f"*State:* {status}\n"
            f"_Mode_: `{escape_md_v2('PAPER' if self._stats['paper_mode'] else 'LIVE')}`\n"
            f"_Exchange_: `{escape_md_v2(self.config.exchange.name.upper())}`\n"
            f"_Health_: `{escape_md_v2(runtime_status.get('state', 'ui-only'))}`"
        )
        await msg.reply_markdown_v2(text, reply_markup=kb)

    async def send_health(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        msg = update.message or update.callback_query.message
        if not is_authorized(update.effective_chat.id):
            await msg.reply_text("Unauthorized", reply_markup=self.main_menu)
            return
        health = self.runtime.status() if self.runtime else {"state": "ui-only", "paper": self.config.paper_trading}
        def value(key: str, default: str = "unknown") -> str:
            return escape_md_v2(str(health.get(key, default)))
        text = (
            "*🩺 Runtime Health*\n\n"
            f"*State:* `{value('state')}`\n"
            f"*Mode:* `{value('paper')}`\n"
            f"*Bridge:* `{value('bridge_connected')}`\n"
            f"*Database:* `{value('database_healthy')}`\n"
            f"*LLM:* `{value('llm_healthy')}`\n"
            f"*Symbols:* `{value('active_symbols')}`\n"
            f"*Errors:* `{value('error_count', '0')}`\n"
            f"*Uptime:* `{value('uptime_seconds', 'not running')}s`\n"
            f"*Emergency latch:* `{value('emergency_latched', 'false')}`\n"
            f"*Stop file:* `{value('emergency_file_present', 'false')}`\n"
            f"*Last scan age:* `{value('last_scan_age_seconds', 'never')}`\n"
            f"*Last error:* `{value('last_error', 'none')}`"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Refresh health", callback_data="refresh:health"),
             InlineKeyboardButton("📜 Events", callback_data="view:events")],
            [InlineKeyboardButton("🛑 Emergency stop", callback_data="emergency_stop"),
             InlineKeyboardButton("🔓 Reset latch", callback_data="request:emergency_reset")],
        ])
        await msg.reply_markdown_v2(text, reply_markup=kb)

    async def send_events(self, update: Update, context: ContextTypes.DEFAULT_TYPE, count: int = 10):
        msg = update.message or update.callback_query.message
        if not is_authorized(update.effective_chat.id):
            await msg.reply_text("Unauthorized", reply_markup=self.main_menu)
            return
        if not self.runtime or not getattr(self.runtime, "state_db", None):
            await msg.reply_text("Runtime event store is unavailable.", reply_markup=self.main_menu)
            return
        events = self.runtime.state_db.get_events(limit=count)
        if not events:
            await msg.reply_text("No persisted runtime events yet.", reply_markup=self.main_menu)
            return
        lines = ["*📜 Runtime Events*", ""]
        for event in events:
            stamp = time.strftime("%H:%M:%S", time.localtime(event.get("created_at", 0)))
            kind = escape_md_v2(event.get("kind", "unknown"))
            symbol = escape_md_v2(event.get("symbol", "") or "-")
            lines.append(f"`{stamp}` *{kind}* `{symbol}`")
        await msg.reply_markdown_v2("\n".join(lines), reply_markup=self.main_menu)

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
        chat_id = update.effective_chat.id
        if not is_authorized(chat_id):
            await query.answer("Unauthorized", show_alert=True)
            return
        await query.answer()

        if query.data == "refresh_status":
            await self.send_status(update, context)
        elif query.data == "close_all":
            await self.execute_close_all(update, context)
        elif query.data.startswith("confirm:"):
            _, action, token = query.data.split(":", 2)
            if action == "close_all":
                await self.confirm_close_all(update, context, token)
            elif action == "emergency_reset":
                await self.confirm_emergency_reset(update, token)
        elif query.data.startswith("cancel:"):
            _, token = query.data.split(":", 1)
            self._consume_confirmation(token, chat_id, "close_all")
            self._consume_confirmation(token, chat_id, "emergency_reset")
            await query.edit_message_text("Confirmation cancelled.", reply_markup=self.main_menu)
        elif query.data == "refresh:health":
            await self.send_health(update, context)
        elif query.data == "view:events":
            await self.send_events(update, context)
        elif query.data == "emergency_stop":
            await self.execute_emergency_stop(update, context)
        elif query.data == "request:emergency_reset":
            await self.request_emergency_reset(update)
        elif query.data.startswith("control:"):
            _, action, token = query.data.split(":", 2)
            if not self._consume_confirmation(token, chat_id, f"control:{action}"):
                await query.edit_message_text("Control action expired or already used.", reply_markup=self.main_menu)
                return
            await self.execute_control(update, context, action)

    async def execute_close_all(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if not is_admin(update.effective_chat.id):
            await query.answer("Admin only", show_alert=True)
            return

        positions = self.bridge.get_positions()
        if not positions:
            await query.answer("No positions to close.", show_alert=True)
            return

        tickets = [{"ticket": p.ticket, "symbol": p.symbol} for p in positions]
        token = self._create_confirmation(update.effective_chat.id, "close_all", {"positions": tickets})
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Yes, close all", callback_data=f"confirm:close_all:{token}"),
             InlineKeyboardButton("Cancel", callback_data=f"cancel:{token}")]
        ])
        await query.message.reply_markdown_v2(
            f"*⚠️ Are you sure you want to close {len(positions)} positions?*\n_Confirmation expires in {self.confirmation_ttl_seconds}s\\.",
            reply_markup=kb,
        )

    async def execute_emergency_stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if not is_admin(update.effective_chat.id):
            await query.answer("Admin only", show_alert=True)
            return
        if self.runtime:
            self.runtime.emergency_stop("emergency stop requested from Telegram button")
            await query.edit_message_text("EMERGENCY STOP engaged. Runtime will not restart until reset.", reply_markup=self.main_menu)
        else:
            await query.edit_message_text("Runtime supervisor is unavailable.", reply_markup=self.main_menu)

    async def request_emergency_reset(self, update: Update):
        query = update.callback_query
        if not is_admin(update.effective_chat.id):
            await query.answer("Admin only", show_alert=True)
            return
        token = self._create_confirmation(update.effective_chat.id, "emergency_reset")
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Confirm reset", callback_data=f"confirm:emergency_reset:{token}"),
             InlineKeyboardButton("Cancel", callback_data=f"cancel:{token}")]
        ])
        await query.edit_message_text(
            f"Reset emergency latch? This does not start the runtime. Expires in {self.confirmation_ttl_seconds}s.",
            reply_markup=kb,
        )

    async def execute_control(self, update: Update, context: ContextTypes.DEFAULT_TYPE, cmd: str):
        query = update.callback_query
        if not is_admin(update.effective_chat.id):
            await query.answer("Admin only", show_alert=True)
            return

        if cmd == "start_scan":
            started = self.runtime.start() if self.runtime else True
            self._stats['scanner_active'] = started
            await query.message.reply_text("▶️ Scanner started." if started else "Scanner is already running or emergency-stopped.")
        elif cmd == "stop_scan":
            stopped = self.runtime.stop() if self.runtime else True
            self._stats['scanner_active'] = False
            await query.message.reply_text("⏹️ Scanner stopped." if stopped else "Scanner is still stopping.")
        elif cmd == "restart_scan":
            if self.runtime:
                self.runtime.stop()
                started = self.runtime.start()
            else:
                started = True
            self._stats['scanner_active'] = started
            await context.bot.send_message(query.message.chat_id, "🔄 Restarting...")
            await context.bot.send_message(query.message.chat_id, "▶️ Scanner restarted." if started else "❌ Scanner restart failed.")

    async def confirm_close_all(self, update: Update, context: ContextTypes.DEFAULT_TYPE, token: str):
        query = update.callback_query
        if not is_admin(update.effective_chat.id):
            await query.answer("Admin only", show_alert=True)
            return
        pending = self._consume_confirmation(token, update.effective_chat.id, "close_all")
        if not pending:
            await query.edit_message_text("Close-all confirmation expired or already used.", reply_markup=self.main_menu)
            return
        positions = pending.get("positions", [])
        closed = 0
        failures = []
        for position in positions:
            ok, message = self.bridge.close_position(position["ticket"], position["symbol"])
            if ok:
                closed += 1
            else:
                failures.append(f"{position['ticket']}: {message}")
        summary = f"Closed {closed}/{len(positions)} positions."
        if failures:
            summary += "\nFailures: " + "; ".join(failures[:5])
        await query.edit_message_text(summary, reply_markup=self.main_menu)

    async def confirm_emergency_reset(self, update: Update, token: str):
        query = update.callback_query
        if not is_admin(update.effective_chat.id):
            await query.answer("Admin only", show_alert=True)
            return
        if not self._consume_confirmation(token, update.effective_chat.id, "emergency_reset"):
            await query.edit_message_text("Reset confirmation expired or already used.", reply_markup=self.main_menu)
            return
        if self.runtime:
            self.runtime.reset_emergency_stop()
            await query.edit_message_text("Emergency stop reset. Runtime remains stopped; use Start when ready.", reply_markup=self.main_menu)
        else:
            await query.edit_message_text("Runtime supervisor is unavailable.", reply_markup=self.main_menu)

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
        application.add_handler(CommandHandler('help', self.on_help))
        application.add_handler(CommandHandler('status', self.send_status))
        application.add_handler(CommandHandler('health', self.on_health_command))
        application.add_handler(CommandHandler('events', self.on_events_command))
        application.add_handler(CommandHandler('balance', self.send_balance))
        application.add_handler(CommandHandler('control', self.send_control))
        application.add_handler(CommandHandler('logs', self.send_logs))
        application.add_handler(CommandHandler('start_scan', self.on_start_scan_command))
        application.add_handler(CommandHandler('stop_scan', self.on_stop_scan_command))
        application.add_handler(CommandHandler('restart_scan', self.on_restart_scan_command))
        application.add_handler(CommandHandler('emergency_stop', self.on_emergency_stop))
        application.add_handler(CommandHandler('approve', self.on_approve))
        application.add_handler(CommandHandler('decline', self.on_decline))
        application.add_handler(CommandHandler('users', self.on_users))
        application.add_handler(CommandHandler('setkeys', self.on_setkeys))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.on_text))
        application.add_handler(CallbackQueryHandler(self._cb_query))

    def start(self):
        if not self.bot_token:
            logger.warning("Telegram bot token not configured")
            return
        self.running = True
        app = ApplicationBuilder().token(self.bot_token).build()
        self.register_commands(app)
        self._app = app
        asyncio.run(app.run_polling())

    def stop(self):
        if self._app:
            try:
                asyncio.run(self._app.stop())
            except RuntimeError:
                pass
        self.running = False

    def send_message(self, chat_id: int, text: str):
        if not self.bot_token or chat_id == 0:
            return
        bot = Bot(token=self.bot_token)
        import asyncio
        try:
            asyncio.create_task(bot.send_message(chat_id=chat_id, text=text))
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
