from __future__ import annotations

import sys
import time
import logging
from typing import Any, List, Dict
from datetime import datetime

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.layout import Layout
from rich.text import Text
from rich.align import Align
from rich.columns import Columns

logger = logging.getLogger(__name__)
console = Console()

class TerminalDashboard:
    def __init__(self, bridge: Any, config: Any, runtime: Any = None):
        self.bridge = bridge
        self.config = config
        self.runtime = runtime
        self.running = False
        self._last_update = 0
        self._logs: List[str] = []
        
    def add_log(self, message: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self._logs.append(f"[{timestamp}] {message}")
        if len(self._logs) > 50:
            self._logs.pop(0)

    def _get_header(self) -> Panel:
        mode = "LIVE" if not self.config.paper_trading else "PAPER"
        exchange = self.config.exchange.name.upper()
        runtime_state = self.runtime.status().get("state", "ui-only") if self.runtime else "ui-only"
        guard_text = ""
        if getattr(self.config.trading, 'news_guard_enabled', False):
            try:
                from trading.news_guard import get_zone_status
                ns = get_zone_status(None, 30, 5)
                guard_text = f" | News: {ns.zone}"
            except Exception:
                pass
        try:
            from llm import budget as llm_budget
            _over, _a, _used, _limit = llm_budget.check('autotrade')
            if _limit > 0:
                guard_text += f" | Budget: {_used}/{_limit}"
        except Exception:
            pass
        
        # Try to get current P/L if available
        try:
            symbol = self.config.trading.symbols[0]
            pl, _, _ = self.bridge.calculate_daily_pl(symbol)
            pnl_color = "green" if pl > 0 else "red" if pl < 0 else "white"
            pnl_text = f"[{pnl_color}]P/L: {pl:+.2f} USDT[/{pnl_color}]"
        except:
            pnl_text = "P/L: ---"

        title = Text("🤖 Vilona AI v2", style="bold magenta")
        content = Text(f" {mode} | {exchange} | Status: {runtime_state.upper()}{guard_text} | {pnl_text} ", style="white")
        
        return Panel(
            Align.center(content),
            title=title,
            border_style="bright_blue",
            padding=(0, 1)
        )

    def _get_log_table(self) -> Table:
        table = Table(show_header=False, box=None, expand=True)
        for log in self._logs[-15:]:
            # Simple color coding based on keywords
            style = "white"
            if "BUY" in log.upper(): style = "green"
            elif "SELL" in log.upper(): style = "red"
            elif "CLOSE" in log.upper(): style = "cyan"
            elif "SCAN" in log.upper(): style = "yellow"
            
            table.add_row(Text(log, style=style))
        return table

    def _get_footer(self) -> Panel:
        uptime = "Calculating..."
        # Guard bridge calls — fatal errors (missing API key) must not crash the thread
        try:
            pos_count = len(self.bridge.get_positions()) if hasattr(self.bridge, 'get_positions') else 0
        except Exception:
            pos_count = 0

        content = Text(
            f"Uptime: {int(time.time() - self._stats_start)}s | "
            f"Positions: {pos_count} | "
            f"Mode: {'PAPER' if self.config.paper_trading else 'LIVE'} | Runtime: {self.runtime.status().get('state', 'ui-only') if self.runtime else 'ui-only'}",
            style="dim white"
        )
        return Panel(Align.center(content), border_style="dim")

    def start(self):
        # Skip live display in headless or non-TTY mode
        if not sys.stdout.isatty() or getattr(self.config, 'headless', False):
            logger.warning("Terminal dashboard: non-TTY or headless mode, skipping live display")
            self.running = False
            return
        self._stats_start = time.time()
        self.running = True

        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body", minimum_size=10),
            Layout(name="footer", size=3),
        )

        with Live(layout, refresh_per_second=1, screen=True) as live:
            while self.running:
                layout["header"].update(self._get_header())
                layout["body"].update(Panel(self._get_log_table(), title="Live Trading Feed", border_style="bright_blue"))
                layout["footer"].update(self._get_footer())
                time.sleep(0.5)

    def stop(self):
        self.running = False
