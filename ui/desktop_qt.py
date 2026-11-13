"""Vilona AI v2 - Fancy Automated Trading Terminal (PyQt6 + pyqtgraph)"""
from __future__ import annotations
import sys
import time as _time
from datetime import datetime

try:
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QPushButton, QLabel, QTableWidget, QTableWidgetItem, QHeaderView,
        QFrame, QGridLayout, QSplitter, QTextEdit, QStatusBar,
        QSystemTrayIcon, QMenu, QStyle, QMessageBox,
        QLineEdit, QComboBox, QDoubleSpinBox,
    )
    from PyQt6.QtCore import (
        Qt, QTimer, pyqtSignal, QThread,
        QPropertyAnimation, QVariantAnimation, QEasingCurve,
        QAbstractAnimation, QRectF,
    )
    from PyQt6.QtGui import QAction, QIcon, QColor, QPalette, QFont, QPainter, QPen
    PYQT6_AVAILABLE = True
except ImportError:
    PYQT6_AVAILABLE = False

import pyqtgraph as pg

from config import get_config
from core.state_db import StateDB
from trading.bridge_ccxt import CCXTBridge
from trading.bridge_mt5 import MT5Bridge

if not PYQT6_AVAILABLE:
    raise ImportError("PyQt6 is required. Install with: pip install PyQt6")

# Palette
BG = "#11111b"; SURFACE = "#1e1e2e"; SURFACE_HI = "#28283c"
BORDER = "#313244"; TEXT = "#cdd6f4"; TEXT_DIM = "#a6adc8"
TEXT_MUTE = "#6c7086"; GREEN = "#a6e3a1"; RED = "#f38ba8"
GOLD = "#f9e2af"; TEAL = "#94e2d5"; MAUVE = "#cba6f7"; YELLOW = "#f5e0dc"
BLUE = "#89b4fa"
pg.setConfigOptions(antialias=True, background=SURFACE, foreground=TEXT_DIM)

def _fmt_amount(amount, currency):
    sym_map = {"USD": "$", "EUR": "\u20ac", "GBP": "\u00a3", "IDR": "Rp ", "JPY": "\u00a5"}
    sym = sym_map.get(currency.upper(), f"{currency.upper()} ") if currency else ""
    return f"{sym}{amount:,.2f}"

# ---- TickerTape ----
class _TickerTape(QWidget):
    def __init__(self, symbols, bridge, parent=None):
        super().__init__(parent)
        self._symbols = symbols; self._bridge = bridge
        self._offset = 0.0
        self._quotes = {}; self._prev = {}
        self.setFixedHeight(34)
        self.setStyleSheet(f"background-color: {SURFACE}; border-bottom: 1px solid {BORDER};")
        self._timer = QTimer(self); self._timer.timeout.connect(self._refresh); self._timer.start(2500)
        self._scroll_timer = QTimer(self); self._scroll_timer.timeout.connect(self.update)
        self._scroll_timer.start(50)
    def _refresh(self):
        for sym in self._symbols:
            try:
                t = self._bridge.get_tick(sym)
                if t: self._quotes[sym] = (t.bid, t.ask)
            except Exception: pass
        self.update()
    def paintEvent(self, ev):
        from PyQt6.QtGui import QPainter, QPen, QColor, QFont
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(SURFACE))
        font = QFont("JetBrains Mono", 10); font.setBold(True); p.setFont(font)
        x = -int(self._offset) % max(1, self.width())
        fm = p.fontMetrics()
        for sym, (bid, ask) in self._quotes.items():
            prev = self._prev.get(sym, bid)
            color = GREEN if bid >= prev else RED
            txt = f" {sym}  {bid:.2f} "
            w = fm.horizontalAdvance(txt) + 30
            p.setPen(QColor(color)); p.drawText(x, 22, txt)
            p.setPen(QColor(TEXT_MUTE))
            p.drawText(x + fm.horizontalAdvance(txt), 22, "\u25b2" if bid >= prev else "\u25bc")
            self._prev[sym] = bid; x += w
            if x > self.width(): break
        p.end()

# ---- Sparkline ----
class _Sparkline(QWidget):
    def __init__(self, color=TEAL, parent=None):
        super().__init__(parent); self._data = []; self._color = color; self.setFixedHeight(28)
    def set_data(self, vals):
        self._data = list(vals)[-40:]; self.update()
    def paintEvent(self, ev):
        from PyQt6.QtGui import QPainter, QPen, QColor
        if len(self._data) < 2: return
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        lo, hi = min(self._data), max(self._data); rng = (hi - lo) or 1.0
        w, h = self.width(), self.height()
        pts = [(i/(len(self._data)-1)*w, h-((v-lo)/rng)*(h-4)-2) for i, v in enumerate(self._data)]
        p.setPen(QPen(QColor(self._color), 1.5))
        for i in range(1, len(pts)):
            p.drawLine(int(pts[i-1][0]), int(pts[i-1][1]), int(pts[i][0]), int(pts[i][1]))
        p.end()

# ---- KPI tile ----
class _KpiTile(QFrame):
    def __init__(self, title, color=TEXT, spark_color=None):
        super().__init__()
        self.setStyleSheet(f"background-color: {SURFACE}; border: 1px solid {BORDER}; border-radius: 10px;")
        lay = QVBoxLayout(self); lay.setContentsMargins(14, 12, 14, 10); lay.setSpacing(2)
        t = QLabel(title.upper())
        t.setStyleSheet(f"color: {TEXT_MUTE}; font-size: 9px; letter-spacing: 1px; font-weight: 600;")
        lay.addWidget(t)
        self._value_lbl = QLabel("\u2014")
        self._value_lbl.setStyleSheet(f"color: {color}; font-size: 20px; font-weight: 700;")
        lay.addWidget(self._value_lbl)
        self._spark = _Sparkline(spark_color or color); lay.addWidget(self._spark)
        self._current = 0.0; self._anim = None; self._history = []
    def animate_number(self, target, currency="USD"):
        if abs(target - self._current) < 0.005: return
        start = self._current; self._current = target
        self._anim = QVariantAnimation(self)
        self._anim.setStartValue(start); self._anim.setEndValue(target)
        self._anim.setDuration(min(600, max(200, int(abs(target - start) / 50) + 200)))
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(lambda v: self._value_lbl.setText(_fmt_amount(v, currency)))
        self._anim.start()
    def push_history(self, v):
        self._history.append(v); self._history = self._history[-40:]; self._spark.set_data(self._history)
    def set_text(self, text, color=TEXT):
        self._value_lbl.setText(text)
        self._value_lbl.setStyleSheet(f"color: {color}; font-size: 20px; font-weight: 700;")
    def flash(self, color):
        self._value_lbl.setStyleSheet(f"color: {color}; font-size: 20px; font-weight: 700;")
        QTimer.singleShot(400, lambda: self._value_lbl.setStyleSheet(f"color: {TEXT}; font-size: 20px; font-weight: 700;"))

# ---- Order ticket ----
class _OrderTicket(QFrame):
    submitted = pyqtSignal(str, str, float, float, float)
    def __init__(self, symbols):
        super().__init__()
        self.setStyleSheet(f"background-color: {SURFACE}; border: 1px solid {BORDER}; border-radius: 10px;")
        lay = QVBoxLayout(self); lay.setContentsMargins(14, 12, 14, 14); lay.setSpacing(8)
        t = QLabel("ORDER TICKET")
        t.setStyleSheet(f"color: {TEXT_DIM}; font-size: 10px; letter-spacing: 1px; font-weight: 600;")
        lay.addWidget(t)
        self.sym_box = QComboBox(); self.sym_box.addItems(symbols or ['XAUUSD'])
        self.sym_box.setStyleSheet(f"background-color: {SURFACE_HI}; color: {TEXT}; border: 1px solid {BORDER}; border-radius: 6px; padding: 6px;")
        lay.addWidget(self.sym_box)
        grid = QGridLayout(); grid.setSpacing(6)
        grid.addWidget(QLabel("Lot"), 0, 0)
        self.lot_edit = QDoubleSpinBox(); self.lot_edit.setRange(0.01, 100.0); self.lot_edit.setDecimals(2)
        grid.addWidget(self.lot_edit, 0, 1)
        grid.addWidget(QLabel("SL"), 1, 0)
        self.sl_edit = QDoubleSpinBox(); self.sl_edit.setRange(0.0, 1e9); self.sl_edit.setDecimals(2)
        grid.addWidget(self.sl_edit, 1, 1)
        grid.addWidget(QLabel("TP"), 2, 0)
        self.tp_edit = QDoubleSpinBox(); self.tp_edit.setRange(0.0, 1e9); self.tp_edit.setDecimals(2)
        grid.addWidget(self.tp_edit, 2, 1)
        for i in range(grid.count()):
            w = grid.itemAt(i).widget()
            if w: w.setStyleSheet(f"color: {TEXT_DIM}; background: transparent; font-size: 11px;")
        lay.addLayout(grid)
        btn_row = QHBoxLayout()
        self.btn_buy = QPushButton("BUY"); self.btn_sell = QPushButton("SELL")
        self.btn_buy.setStyleSheet(f"background-color: {GREEN}; color: {BG}; font-weight: 700; border-radius: 6px; padding: 10px;")
        self.btn_sell.setStyleSheet(f"background-color: {RED}; color: {BG}; font-weight: 700; border-radius: 6px; padding: 10px;")
        self.btn_buy.clicked.connect(lambda: self._submit('buy'))
        self.btn_sell.clicked.connect(lambda: self._submit('sell'))
        btn_row.addWidget(self.btn_buy); btn_row.addWidget(self.btn_sell)
        lay.addLayout(btn_row)
    def _submit(self, side):
        self.submitted.emit(side, self.sym_box.currentText(),
                            float(self.lot_edit.value()), float(self.sl_edit.value()), float(self.tp_edit.value()))

# ---- Card ----
class _Card(QFrame):
    def __init__(self, title=""):
        super().__init__()
        self.setStyleSheet(f"background-color: {SURFACE}; border: 1px solid {BORDER}; border-radius: 10px;")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(12, 10, 12, 10); self._layout.setSpacing(8)
        if title:
            lbl = QLabel(title.upper())
            lbl.setStyleSheet(f"color: {TEXT_DIM}; font-size: 10px; letter-spacing: 1px; font-weight: 600;")
            self._layout.addWidget(lbl)

# ---- Main window ----
class VilonaMainWindow(QMainWindow):
    def __init__(self, bridge, config, state_db):
        super().__init__()
        self.bridge = bridge; self.config = config; self.state_db = state_db
        self.symbols = config.trading.symbols or ['XAUUSD']
        self.running = False; self._currency = ''; self._pulse_state = False
        self.setWindowTitle("Vilona AI v2 \u2014 Trading Terminal")
        self.setGeometry(60, 40, 1560, 960)
        self._build_ui(); self._setup_tray(); self._apply_styles()
        self._kpi_tiles = [self.kpi_balance, self.kpi_equity, self.kpi_daily_pl,
                           self.kpi_winrate, self.kpi_positions]
        for i, tile in enumerate(self._kpi_tiles):
            tile.setWindowOpacity(0.0); self._fade_in(tile, delay_ms=i * 100)
        self._pulse_timer = QTimer(self); self._pulse_timer.timeout.connect(self._pulse_dot)
        self._pulse_timer.start(900)
        self.refresh_worker = None; self._start_refresh()

    def _build_ui(self):
        central = QWidget(); self.setCentralWidget(central)
        root = QVBoxLayout(central); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)
        self.ticker = _TickerTape(self.symbols, self.bridge)
        root.addWidget(self.ticker)
        body = QWidget(); body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(16, 14, 16, 12); body_lay.setSpacing(12)
        root.addWidget(body, 1)
        kpi_row = QHBoxLayout(); kpi_row.setSpacing(12)
        self.kpi_balance = _KpiTile("Account Balance", TEAL, TEAL)
        self.kpi_equity = _KpiTile("Equity", TEXT, BLUE)
        self.kpi_daily_pl = _KpiTile("Today's P/L", GREEN, GREEN)
        self.kpi_winrate = _KpiTile("Win Rate", MAUVE, MAUVE)
        self.kpi_positions = _KpiTile("Open Positions", YELLOW, YELLOW)
        self._kpi_tiles = [self.kpi_balance, self.kpi_equity, self.kpi_daily_pl, self.kpi_winrate, self.kpi_positions]
        for k in self._kpi_tiles: kpi_row.addWidget(k, 1)
        body_lay.addLayout(kpi_row)
        hsplit = QHBoxLayout(); hsplit.setSpacing(12)
        left = QVBoxLayout(); left.setSpacing(12)
        chart_card = _Card("")
        self.plot = pg.PlotWidget(); self.plot.setBackground(SURFACE)
        self.plot.showGrid(x=True, y=True, alpha=0.15)
        self.plot.getAxis('bottom').setPen(pg.mkPen(QColor(BORDER)))
        self.plot.getAxis('left').setPen(pg.mkPen(QColor(BORDER)))
        chart_card._layout.addWidget(self.plot)
        left.addWidget(chart_card, 3)
        pos_card = _Card("Open Positions")
        self.pos_table = QTableWidget(); self.pos_table.setColumnCount(9)
        self.pos_table.setHorizontalHeaderLabels(["Ticket","Symbol","Type","Volume","Entry","Current","SL","TP","P/L"])
        hdr = self.pos_table.horizontalHeader()
        for i in range(9): hdr.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)
        self.pos_table.setAlternatingRowColors(True)
        self.pos_table.verticalHeader().setVisible(False); self.pos_table.setShowGrid(False)
        self.pos_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        pos_card._layout.addWidget(self.pos_table); left.addWidget(pos_card, 2)
        hsplit.addLayout(left, 4)
        right = QVBoxLayout(); right.setSpacing(12)
        self.ticket = _OrderTicket(self.symbols); self.ticket.submitted.connect(self._submit_order)
        right.addWidget(self.ticket)
        scanner_card = _Card("Scanner"); sl = scanner_card._layout
        self.status_dot = QLabel("\u25cf Disconnected")
        self.status_dot.setStyleSheet(f"color: {RED}; font-size: 15px; font-weight: 700;")
        sl.addWidget(self.status_dot)
        self._symbol_label = QLabel(f"Symbols: {', '.join(self.symbols)}")
        self._symbol_label.setStyleSheet(f"color: {TEXT_DIM}; font-size: 11px;")
        sl.addWidget(self._symbol_label)
        self.btn_start = QPushButton("\u25b6  Start Scanner")
        self.btn_start.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_start.clicked.connect(self.start_scanner); sl.addWidget(self.btn_start)
        self.btn_stop = QPushButton("\u23f9  Stop Scanner")
        self.btn_stop.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_stop.clicked.connect(self.stop_scanner); self.btn_stop.setEnabled(False)
        sl.addWidget(self.btn_stop)
        self.btn_close_all = QPushButton("\u26a0  Close All")
        self.btn_close_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close_all.clicked.connect(self.close_all); sl.addWidget(self.btn_close_all)
        right.addWidget(scanner_card)
        info_card = _Card("Market Info")
        self._symbol_info_label = QLabel("\u2014"); self._symbol_info_label.setWordWrap(True)
        self._symbol_info_label.setStyleSheet(f"color: {TEXT_DIM}; font-size: 11px;")
        info_card._layout.addWidget(self._symbol_info_label)
        right.addWidget(info_card)
        log_card = _Card("System Log")
        self.log_text = QTextEdit(); self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("JetBrains Mono", 9))
        log_card._layout.addWidget(self.log_text); right.addWidget(log_card, 1)
        hsplit.addLayout(right, 1)
        body_lay.addLayout(hsplit, 1)
        self.statusBar().showMessage("Ready")

    def _update_chart(self, symbol, candles):
        if not candles: return
        self.plot.clear()
        n = len(candles)
        for i in range(n):
            c = candles[i]
            o, cl, h, l = c['open'], c['close'], c['high'], c['low']
            pen = pg.mkPen(QColor(GREEN) if cl >= o else QColor(RED), width=1)
            brush = pg.mkBrush(QColor(GREEN) if cl >= o else QColor(RED))
            self.plot.plot([i, i], [l, h], pen=pen)
            item = pg.QtWidgets.QGraphicsRectItem(QRectF(i - 0.35, min(o, cl), 0.7, max(0.0001, abs(cl - o))))
            item.setPen(pen); item.setBrush(brush); self.plot.addItem(item)
        try:
            positions = [p for p in self.bridge.get_positions(symbol)]
            if positions:
                pos = positions[0]
                if pos.sl:
                    self.plot.addItem(pg.InfiniteLine(pos=pos.sl, angle=0, pen=pg.mkPen(QColor(RED), style=Qt.PenStyle.DashLine)))
                if pos.tp:
                    self.plot.addItem(pg.InfiniteLine(pos=pos.tp, angle=0, pen=pg.mkPen(QColor(GREEN), style=Qt.PenStyle.DashLine)))
        except Exception: pass
        self.plot.setTitle(f"<span style='color:{TEXT_DIM};font-size:11pt'>{symbol} M15 last={candles[-1]['close']:.2f}</span>")

    def _fade_in(self, widget, delay_ms=0):
        anim = QPropertyAnimation(widget, b"windowOpacity")
        anim.setStartValue(0.0); anim.setEndValue(1.0)
        anim.setDuration(450); anim.setEasingCurve(QEasingCurve.Type.OutBack)
        QTimer.singleShot(delay_ms, anim.start)
        widget._fade_anim = anim

    def _pulse_dot(self):
        connected = self.bridge.is_connected()
        color = GREEN if connected else RED
        self._pulse_state = not self._pulse_state
        opacity = 1.0 if self._pulse_state else 0.45
        self.status_dot.setStyleSheet(f"color: {color}; font-size: 15px; font-weight: 700; opacity: {opacity};")

    def _setup_tray(self):
        self.tray = QSystemTrayIcon(self)
        icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        self.tray.setIcon(icon); self.tray.setVisible(True)
        tray_menu = QMenu()
        show_a = QAction("Show", self); show_a.triggered.connect(self.show)
        hide_a = QAction("Hide", self); hide_a.triggered.connect(self.hide)
        quit_a = QAction("Quit", self); quit_a.triggered.connect(self.close)
        tray_menu.addAction(show_a); tray_menu.addAction(hide_a); tray_menu.addSeparator(); tray_menu.addAction(quit_a)
        self.tray.setContextMenu(tray_menu)

    def _apply_styles(self):
        self.setStyleSheet(f"""
            QMainWindow {{ background-color: {BG}; }}
            QGroupBox {{ color: {TEXT_DIM}; font-weight: 600; border: 1px solid {BORDER}; border-radius: 10px; margin-top: 10px; padding-top: 10px; }}
            QTableWidget {{ background-color: {SURFACE}; alternate-background-color: {SURFACE_HI}; color: {TEXT}; gridline-color: {BORDER}; border: none; border-radius: 6px; selection-background-color: {MAUVE}; selection-color: {BG}; }}
            QHeaderView::section {{ background-color: {SURFACE_HI}; color: {TEXT_MUTE}; padding: 6px 5px; font-weight: 600; font-size: 10px; border: none; border-bottom: 1px solid {BORDER}; }}
            QPushButton {{ border: none; border-radius: 8px; padding: 11px 16px; font-size: 12px; font-weight: 600; color: {BG}; }}
            QPushButton:disabled {{ background-color: {BORDER}; color: {TEXT_MUTE}; }}
            QTextEdit {{ background-color: {SURFACE}; color: {TEXT}; border: none; border-radius: 6px; font-family: 'JetBrains Mono', 'Consolas', monospace; font-size: 10px; }}
            QLabel {{ color: {TEXT}; }}
            QComboBox QAbstractItemView {{ background: {SURFACE_HI}; color: {TEXT}; selection-background-color: {MAUVE}; selection-color: {BG}; border: 1px solid {BORDER}; }}
            QDoubleSpinBox {{ background-color: {SURFACE_HI}; color: {TEXT}; border: 1px solid {BORDER}; border-radius: 6px; padding: 5px; }}
            QStatusBar {{ background-color: {SURFACE}; color: {TEXT_MUTE}; }}
            QScrollBar::vertical {{ background: {SURFACE_HI}; width: 6px; border-radius: 3px; }}
            QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 3px; min-height: 30px; }}
        """)
        self.btn_start.setStyleSheet(f"background-color: {GREEN}; color: {BG}; padding: 11px 16px; border-radius: 8px; font-weight: 700; font-size: 12px;")
        self.btn_stop.setStyleSheet(f"background-color: {BORDER}; color: {TEXT_MUTE}; padding: 11px 16px; border-radius: 8px; font-weight: 700; font-size: 12px;")
        self.btn_close_all.setStyleSheet(f"background-color: {YELLOW}; color: {BG}; padding: 11px 16px; border-radius: 8px; font-weight: 700; font-size: 12px;")

    def _start_refresh(self):
        self.refresh_worker = DataRefreshWorker(self.bridge, self.symbols)
        self.refresh_worker.data_ready.connect(self._on_data)
        self.refresh_worker.start(); self._log("Data refresh started")

    def _on_data(self, data):
        positions = data.get('positions', [])
        currency = data.get('currency', 'USD') or 'USD'
        self._currency = currency
        bal = data.get('balance', 0.0)
        self.kpi_balance.animate_number(bal, currency); self.kpi_balance.push_history(bal)
        self.kpi_equity.animate_number(bal, currency)
        pl = data.get('daily_pl', 0.0)
        pl_color = GREEN if pl >= 0 else RED
        self.kpi_daily_pl.animate_number(pl, currency)
        self.kpi_daily_pl._value_lbl.setStyleSheet(f"color: {pl_color}; font-size: 20px; font-weight: 700;")
        self.kpi_daily_pl.push_history(pl)
        wins = data.get('wins', 0); total = data.get('total', 0)
        wr = wins / total * 100 if total else 0.0
        self.kpi_winrate.set_text(f"{wr:.1f}%  ({wins}/{total})", MAUVE)
        n_pos = len(positions)
        if self.kpi_positions._value_lbl.text() != str(n_pos): self.kpi_positions.flash(YELLOW)
        self.kpi_positions._value_lbl.setText(str(n_pos))
        self.pos_table.setRowCount(len(positions))
        for row, pos in enumerate(positions):
            self.pos_table.setItem(row, 0, QTableWidgetItem(str(pos.ticket)))
            self.pos_table.setItem(row, 1, QTableWidgetItem(pos.symbol))
            self.pos_table.setItem(row, 2, QTableWidgetItem(pos.type.upper()))
            self.pos_table.setItem(row, 3, QTableWidgetItem(f"{pos.volume:.2f}"))
            self.pos_table.setItem(row, 4, QTableWidgetItem(f"{pos.price_open:.2f}"))
            self.pos_table.setItem(row, 5, QTableWidgetItem(f"{pos.price_current:.2f}"))
            self.pos_table.setItem(row, 6, QTableWidgetItem(f"{pos.sl:.2f}" if pos.sl else "\u2014"))
            self.pos_table.setItem(row, 7, QTableWidgetItem(f"{pos.tp:.2f}" if pos.tp else "\u2014"))
            item = QTableWidgetItem(f"{'+' if pos.profit > 0 else ''}{pos.profit:.2f}")
            item.setForeground(QColor(GREEN if pos.profit >= 0 else RED))
            self.pos_table.setItem(row, 8, item)
        try:
            candles = self.bridge.get_candles(self.symbols[0], '15m', limit=120) or []
            self._update_chart(self.symbols[0], candles)
        except Exception: pass
        try:
            info = self.bridge.get_symbol_info(self.symbols[0])
            if info: self._symbol_info_label.setText(f"{info.symbol} digits={info.digits} lot_min={info.lot_min}")
        except Exception: pass
        if self.bridge.is_connected():
            self.status_dot.setText("\u25cf Connected")
            self.status_dot.setStyleSheet(f"color: {GREEN}; font-size: 15px; font-weight: 700;")
        else:
            self.status_dot.setText("\u25cf Disconnected")
            self.status_dot.setStyleSheet(f"color: {RED}; font-size: 15px; font-weight: 700;")

    def _submit_order(self, side, symbol, lot, sl, tp):
        self._log(f"Order: {side.upper()} {symbol} {lot} lots SL={sl} TP={tp}")
        try:
            result = self.bridge.place_market_order(symbol, side, lot, sl, tp)
            self._log(f"Order result: {result}")
        except Exception as e:
            self._log(f"Order failed: {e}")

    def start_scanner(self):
        self.running = True; self.btn_start.setEnabled(False); self.btn_stop.setEnabled(True)
        self.btn_stop.setStyleSheet(f"background-color: {RED}; color: {BG}; padding: 11px 16px; border-radius: 8px; font-weight: 700; font-size: 12px;")
        self._log("Scanner started")

    def stop_scanner(self):
        self.running = False; self.btn_start.setEnabled(True); self.btn_stop.setEnabled(False)
        self.btn_stop.setStyleSheet(f"background-color: {BORDER}; color: {TEXT_MUTE}; padding: 11px 16px; border-radius: 8px; font-weight: 700; font-size: 12px;")
        self._log("Scanner stopped")

    def close_all(self):
        positions = self.bridge.get_positions()
        reply = QMessageBox.question(self, 'Confirm Close All', f"Close all {len(positions)} positions?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            try:
                for pos in positions: self.bridge.close_position(pos.ticket, pos.symbol)
                self._log(f"Closed {len(positions)} positions")
            except Exception as e:
                self._log(f"Error closing positions: {e}")

    def _log(self, message):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{ts}] {message}")

    def closeEvent(self, event):
        if self.refresh_worker: self.refresh_worker.stop()
        event.accept()

# ---- Background data refresh ----
class DataRefreshWorker(QThread):
    data_ready = pyqtSignal(dict)

    def __init__(self, bridge, symbols):
        super().__init__()
        self.bridge = bridge
        self.symbols = symbols
        self.running = True

    def run(self):
        while self.running:
            data = {'positions': [], 'daily_pl': 0.0, 'wins': 0, 'total': 0,
                    'balance': 0.0, 'currency': ''}
            try:
                data['positions'] = self.bridge.get_positions()
                sym = self.symbols[0] if self.symbols else 'XAUUSD'
                data['daily_pl'], data['wins'], data['total'] = \
                    self.bridge.calculate_daily_pl(sym)
                if hasattr(self.bridge, 'get_balance'):
                    bal = self.bridge.get_balance()
                    data['balance'] = bal.get('equity', bal.get('balance', 0.0))
                    data['currency'] = bal.get('currency', 'USD')
                elif hasattr(self.bridge, '_exchange') and self.bridge._exchange:
                    bal = self.bridge._exchange.fetch_balance()
                    data['balance'] = bal.get('total', {}).get('USDT', 0.0)
                    data['currency'] = 'USDT'
            except Exception:
                pass
            self.data_ready.emit(data)
            self.msleep(2500)

    def stop(self):
        self.running = False
        self.wait()


def main():
    app = QApplication(sys.argv); app.setStyle('Fusion')
    cfg = get_config(); state_db = StateDB()
    bridge = MT5Bridge() if cfg.exchange.name.lower() == 'mt5' else CCXTBridge(cfg.exchange)
    if not bridge.connect():
        print("Failed to connect"); return 1
    window = VilonaMainWindow(bridge, cfg, state_db); window.show()
    return app.exec()

if __name__ == "__main__":
    sys.exit(main())
