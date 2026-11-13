"""Vilona AI v2 — Trading Terminal UI (KingAI design system)

Uses the Royal War-Room design: obsidian black, blood red glow, gold crown
accents. Custom-painted HudCard, CommandButton, StatTile, KButton widgets.
"""
from __future__ import annotations

import sys
from datetime import datetime

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTableWidget, QTableWidgetItem, QHeaderView,
    QFrame, QGridLayout, QSplitter, QTextEdit, QStatusBar,
    QSystemTrayIcon, QMenu, QStyle, QMessageBox,
    QLineEdit, QComboBox, QDoubleSpinBox, QSizePolicy,
)
from PySide6.QtCore import (
    Qt, QTimer, Signal, QThread, QPropertyAnimation, QEasingCurve, QRectF,
)
from PySide6.QtGui import QAction, QIcon, QColor, QPalette, QFont, QPainter

import pyqtgraph as pg

from config import get_config, DATA_DIR
from core.state_db import StateDB
from trading.bridge_ccxt import CCXTBridge
from trading.bridge_mt5 import MT5Bridge

from ui.kingai_theme import theme as T
from ui.kingai_theme import fx
from ui.kingai_theme.widgets import (
    HudCard, StatTile, KButton, CommandButton, Chip, caps, note,
    field_label, hbox,
)
from ui.kingai_theme.chrome import NavRail

pg.setConfigOptions(antialias=True, background=T.SURFACE if hasattr(T, 'SURFACE') else '#090406',
                    foreground=T.TEXT)

# KingAI palette (from theme.py)
BG = T.BG
GREEN = T.GREEN
RED = T.RED
AMBER = T.AMBER
GOLD = T.GOLD
CYAN = T.CYAN
TEXT = T.TEXT
TEXT_DIM = T.TEXT_DIM
TEXT_MUTE = T.TEXT_MUTE


class DataRefreshWorker(QThread):
    data_ready = Signal(dict)

    def __init__(self, bridge, symbols):
        super().__init__()
        self.bridge = bridge
        self.symbols = symbols
        self.running = True

    def run(self):
        while self.running:
            data = {'positions': [], 'daily_pl': 0.0, 'wins': 0, 'total': 0,
                    'balance': 0.0, 'currency': '', 'candles': [],
                    'ticker_quotes': {}, 'symbol_info': None}
            try:
                data['positions'] = self.bridge.get_positions()
                sym = self.symbols[0] if self.symbols else 'XAUUSD'
                data['daily_pl'], data['wins'], data['total'] = \
                    self.bridge.calculate_daily_pl(sym)
                data['candles'] = self.bridge.get_candles(sym, '15m', limit=120) or []
                if hasattr(self.bridge, 'get_balance'):
                    bal = self.bridge.get_balance()
                    data['balance'] = bal.get('equity', bal.get('balance', 0.0))
                    data['currency'] = bal.get('currency', 'USD')
                elif hasattr(self.bridge, '_exchange') and self.bridge._exchange:
                    bal = self.bridge._exchange.fetch_balance()
                    data['balance'] = bal.get('total', {}).get('USDT', 0.0)
                    data['currency'] = 'USDT'
                quotes = {}
                for sym in self.symbols:
                    try:
                        t = self.bridge.get_tick(sym)
                        if t: quotes[sym] = (t.bid, t.ask)
                    except Exception: pass
                data['ticker_quotes'] = quotes
                try:
                    info = self.bridge.get_symbol_info(sym)
                    if info:
                        data['symbol_info'] = {
                            'symbol': info.symbol, 'digits': info.digits,
                            'lot_min': info.lot_min}
                except Exception: pass
            except Exception: pass
            self.data_ready.emit(data)
            self.msleep(2500)

    def stop(self):
        self.running = False
        self.wait()


class VilonaMainWindow(QMainWindow):
    def __init__(self, bridge, config, state_db):
        super().__init__()
        self.bridge = bridge
        self.config = config
        self.state_db = state_db
        self.symbols = config.trading.symbols or ['XAUUSD']
        self.running = False
        self._currency = ''

        self.setWindowTitle("Vilona AI v2 — Trading Terminal")
        self.setGeometry(60, 40, 1560, 960)
        self._build_ui()
        self._setup_tray()
        self.setStyleSheet(T.app_stylesheet())

        self.refresh_worker = None
        self._start_refresh()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Nav rail
        self.nav = NavRail()
        root.addWidget(self.nav)

        # Main content
        content = QWidget()
        content_lay = QVBoxLayout(content)
        content_lay.setContentsMargins(16, 12, 16, 12)
        content_lay.setSpacing(12)
        root.addWidget(content, 1)

        # KPI row with StatTiles
        kpi_row = hbox(None, spacing=12)
        self.kpi_balance = StatTile("Account Balance", accent=T.GOLD, big=True)
        self.kpi_equity = StatTile("Equity", accent=T.CYAN, big=True)
        self.kpi_daily_pl = StatTile("Today's P/L", accent=T.GREEN, big=True)
        self.kpi_winrate = StatTile("Win Rate", accent=T.MAUVE if hasattr(T, 'MAUVE') else T.CYAN, big=True)
        self.kpi_positions = StatTile("Open Positions", accent=T.AMBER, big=True)
        kpi_row.addWidget(self.kpi_balance)
        kpi_row.addWidget(self.kpi_equity)
        kpi_row.addWidget(self.kpi_daily_pl)
        kpi_row.addWidget(self.kpi_winrate)
        kpi_row.addWidget(self.kpi_positions)
        content_lay.addLayout(kpi_row)

        # Main split
        hsplit = QHBoxLayout()
        hsplit.setSpacing(12)

        # Left: chart + positions + log
        left = QVBoxLayout()
        left.setSpacing(12)

        chart_card = HudCard(self.symbols[0] if self.symbols else 'XAUUSD',
                             accent=T.GOLD)
        self.plot = pg.PlotWidget()
        self.plot.setBackground('#090406')
        self.plot.showGrid(x=True, y=True, alpha=0.12)
        self.plot.getAxis('bottom').setPen(pg.mkPen(QColor(T.LINE)))
        self.plot.getAxis('left').setPen(pg.mkPen(QColor(T.LINE)))
        self.plot.getAxis('left').setTextPen(QColor(T.TEXT_DIM))
        self.plot.getAxis('bottom').setTextPen(QColor(T.TEXT_DIM))
        chart_card.body.addWidget(self.plot)
        left.addWidget(chart_card, 3)

        pos_card = HudCard("Open Positions", accent=T.RED)
        self.pos_table = QTableWidget()
        self.pos_table.setColumnCount(9)
        self.pos_table.setHorizontalHeaderLabels(
            ["Ticket", "Symbol", "Type", "Volume", "Entry",
             "Current", "SL", "TP", "P/L"])
        hdr = self.pos_table.horizontalHeader()
        for i in range(9):
            hdr.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)
        self.pos_table.setAlternatingRowColors(True)
        self.pos_table.verticalHeader().setVisible(False)
        self.pos_table.setShowGrid(False)
        self.pos_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        pos_card.body.addWidget(self.pos_table)
        left.addWidget(pos_card, 2)

        hsplit.addLayout(left, 4)

        # Right: command button, order ticket, scanner, info, log
        right = QVBoxLayout()
        right.setSpacing(12)

        # Command button (big START/STOP)
        self.cmd_btn = CommandButton()
        self.cmd_btn.set_state('start', 'START')
        self.cmd_btn.clicked.connect(self._toggle_scanner)
        right.addWidget(self.cmd_btn)

        # Scanner status
        self.status_chip = Chip("Disconnected")
        right.addWidget(self.status_chip)

        # Order ticket as HudCard
        order_card = HudCard("Order Ticket", accent=T.RED)
        order_body = order_card.body
        order_body.addWidget(field_label("Symbol"))
        self.sym_box = QComboBox()
        for sym in self.symbols:
            self.sym_box.addItem(sym)
        order_body.addWidget(self.sym_box)
        order_body.addWidget(field_label("Lot"))
        self.lot_edit = QDoubleSpinBox()
        self.lot_edit.setRange(0.01, 100.0)
        self.lot_edit.setDecimals(2)
        self.lot_edit.setValue(0.01)
        order_body.addWidget(self.lot_edit)
        order_body.addWidget(field_label("SL"))
        self.sl_edit = QDoubleSpinBox()
        self.sl_edit.setRange(0.0, 1e9)
        self.sl_edit.setDecimals(2)
        order_body.addWidget(self.sl_edit)
        order_body.addWidget(field_label("TP"))
        self.tp_edit = QDoubleSpinBox()
        self.tp_edit.setRange(0.0, 1e9)
        self.tp_edit.setDecimals(2)
        order_body.addWidget(self.tp_edit)
        self.btn_buy = KButton("BUY", 'primary')
        self.btn_sell = KButton("SELL", 'danger')
        self.btn_buy.clicked.connect(lambda: self._submit_order('buy'))
        self.btn_sell.clicked.connect(lambda: self._submit_order('sell'))
        order_body.addLayout(hbox(self.btn_buy, self.btn_sell, spacing=6))
        right.addWidget(order_card)

        # Market info
        info_card = HudCard("Market Info", accent=T.CYAN)
        self._symbol_info_label = note('—')
        info_card.body.addWidget(self._symbol_info_label)
        right.addWidget(info_card)

        # Log
        log_card = HudCard("System Log", accent=T.GREEN)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(T.font(8, mono=True))
        log_card.body.addWidget(self.log_text)
        right.addWidget(log_card, 1)

        hsplit.addLayout(right, 1)
        content_lay.addLayout(hsplit, 1)

        self.statusBar().showMessage("Ready")

    def _toggle_scanner(self):
        if self.running:
            self.stop_scanner()
        else:
            self.start_scanner()

    def _update_chart(self):
        try:
            sym = self.symbols[0] if self.symbols else 'XAUUSD'
            candles = self.bridge.get_candles(sym, '15m', limit=120) or []
            if not candles: return
            self.plot.clear()
            for i, c in enumerate(candles):
                o, cl, h, l = c['open'], c['close'], c['high'], c['low']
                color = T.GREEN if cl >= o else T.RED
                pen = pg.mkPen(QColor(color), width=0.8)
                self.plot.plot([i, i], [l, h], pen=pen)
                rect = pg.QtWidgets.QGraphicsRectItem(
                    QRectF(i - 0.35, min(o, cl), 0.7, max(0.1, abs(cl - o))))
                rect.setPen(pen); rect.setBrush(pg.mkBrush(QColor(color)))
                self.plot.addItem(rect)
            self.plot.setTitle(f"<span style='color:{T.TEXT_DIM};font-size:11pt'>"
                              f"{sym} M15 last={candles[-1]['close']:.2f}</span>")
        except Exception:
            pass

    def _fade_in(self, widget, delay_ms=0):
        anim = QPropertyAnimation(widget, b"windowOpacity")
        anim.setStartValue(0.0); anim.setEndValue(1.0)
        anim.setDuration(450); anim.setEasingCurve(QEasingCurve.Type.OutBack)
        QTimer.singleShot(delay_ms, anim.start)
        widget._fade_anim = anim

    def _setup_tray(self):
        self.tray = QSystemTrayIcon(self)
        icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        self.tray.setIcon(icon); self.tray.setVisible(True)
        tray_menu = QMenu()
        show_a = QAction("Show", self); show_a.triggered.connect(self.show)
        hide_a = QAction("Hide", self); hide_a.triggered.connect(self.hide)
        quit_a = QAction("Quit", self); quit_a.triggered.connect(self.close)
        tray_menu.addAction(show_a); tray_menu.addAction(hide_a)
        tray_menu.addSeparator(); tray_menu.addAction(quit_a)
        self.tray.setContextMenu(tray_menu)

    def _start_refresh(self):
        self.refresh_worker = DataRefreshWorker(self.bridge, self.symbols)
        self.refresh_worker.data_ready.connect(self._on_data)
        self.refresh_worker.start()
        self.log("Data refresh started")

    def _on_data(self, data):
        positions = data.get('positions', [])
        currency = data.get('currency', 'USD') or 'USD'
        self._currency = currency
        bal = data.get('balance', 0.0)
        self.kpi_balance.set_value(bal, color=T.GOLD)
        self.kpi_equity.set_value(bal, color=T.CYAN)
        pl = data.get('daily_pl', 0.0)
        pl_color = T.GREEN if pl >= 0 else T.RED
        self.kpi_daily_pl.set_value(pl, color=pl_color)
        wins = data.get('wins', 0); total = data.get('total', 0)
        wr = wins / total * 100 if total else 0.0
        self.kpi_winrate.set_value(wr, fmt='{:.1f}%', color=T.GREEN if wr >= 50 else T.AMBER)
        n_pos = len(positions)
        self.kpi_positions.set_value(n_pos, fmt='{:,.0f}', color=T.AMBER)
        self.pos_table.setRowCount(len(positions))
        for row, pos in enumerate(positions):
            self.pos_table.setItem(row, 0, QTableWidgetItem(str(pos.ticket)))
            self.pos_table.setItem(row, 1, QTableWidgetItem(pos.symbol))
            self.pos_table.setItem(row, 2, QTableWidgetItem(pos.type.upper()))
            self.pos_table.setItem(row, 3, QTableWidgetItem(f"{pos.volume:.2f}"))
            self.pos_table.setItem(row, 4, QTableWidgetItem(f"{pos.price_open:.2f}"))
            self.pos_table.setItem(row, 5, QTableWidgetItem(f"{pos.price_current:.2f}"))
            self.pos_table.setItem(row, 6, QTableWidgetItem(f"{pos.sl:.2f}" if pos.sl else "—"))
            self.pos_table.setItem(row, 7, QTableWidgetItem(f"{pos.tp:.2f}" if pos.tp else "—"))
            item = QTableWidgetItem(f"{'+' if pos.profit > 0 else ''}{pos.profit:.2f}")
            item.setForeground(QColor(T.GREEN if pos.profit >= 0 else T.RED))
            self.pos_table.setItem(row, 8, item)
        try:
            candles = self.bridge.get_candles(self.symbols[0], '15m', limit=120) or []
            if candles:
                self.plot.clear()
                for i, c in enumerate(candles):
                    o, cl, h, l = c['open'], c['close'], c['high'], c['low']
                    color = T.GREEN if cl >= o else T.RED
                    pen = pg.mkPen(QColor(color), width=0.8)
                    self.plot.plot([i, i], [l, h], pen=pen)
                    rect = pg.QtWidgets.QGraphicsRectItem(
                        QRectF(i - 0.35, min(o, cl), 0.7, max(0.1, abs(cl - o))))
                    rect.setPen(pen); rect.setBrush(pg.mkBrush(QColor(color)))
                    self.plot.addItem(rect)
                self.plot.setTitle(f"<span style='color:{T.TEXT_DIM};font-size:11pt'>"
                                  f"{self.symbols[0]} M15 last={candles[-1]['close']:.2f}</span>")
        except Exception:
            pass
        if 'ticker_quotes' in data and data['ticker_quotes']:
            if hasattr(self, 'ticker') and hasattr(self.ticker, '_quotes'):
                self.ticker._quotes = data['ticker_quotes']
        try:
            info = data.get('symbol_info')
            if info:
                self._symbol_info_label.setText(
                    f"{info['symbol']} digits={info['digits']} lot_min={info['lot_min']}")
        except Exception:
            pass

    def _submit_order(self, side, symbol, lot, sl, tp):
        self.log(f"Order: {side.upper()} {symbol} {lot} SL={sl} TP={tp}")

    def start_scanner(self):
        self.running = True
        if hasattr(self, 'cmd_btn'): self.cmd_btn.set_state('stop', 'STOP')
        self._log("Scanner started")

    def stop_scanner(self):
        self.running = False
        if hasattr(self, 'cmd_btn'): self.cmd_btn.set_state('start', 'START')
        self._log("Scanner stopped")

    def _toggle_scanner(self):
        if self.running:
            self.stop_scanner()
        else:
            self.start_scanner()

    def close_all(self):
        positions = self.bridge.get_positions()
        reply = QMessageBox.question(self, 'Confirm Close All',
            f"Close all {len(positions)} positions?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            try:
                for pos in positions:
                    self.bridge.close_position(pos.ticket, pos.symbol)
                self.log(f"Closed {len(positions)} positions")
            except Exception as e:
                self.log(f"Error closing positions: {e}")

    def log(self, message):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{ts}] {message}")

    def closeEvent(self, event):
        if self.refresh_worker:
            self.refresh_worker.stop()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    cfg = get_config()
    state_db = StateDB()
    bridge = MT5Bridge() if cfg.exchange.name.lower() == 'mt5' else CCXTBridge(cfg.exchange)
    if not bridge.connect():
        print("Failed to connect to exchange")
        return 1
    if cfg.exchange.name.lower() == 'mt5':
        cfg.trading.symbols = bridge.get_available_symbols()
    window = VilonaMainWindow(bridge, cfg, state_db)
    window.show()
    return app.exec()

if __name__ == "__main__":
    sys.exit(main())
