"""Vilona AI v2 — Fancy Automated Trading Terminal (PyQt6 + pyqtgraph)

Fully dynamic: ticker tape scrolls live prices, candlestick chart updates
every refresh cycle, KPI tiles animate count-up + sparkline, positions
table, order ticket, system log. MT5 + CCXT bridges supported.
"""
from __future__ import annotations
import sys, time as _t, datetime as _dt, logging

try:
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QPushButton, QLabel, QTableWidget, QTableWidgetItem, QHeaderView,
        QFrame, QGridLayout, QSplitter, QTextEdit, QStatusBar,
        QSystemTrayIcon, QMenu, QStyle, QMessageBox,
        QLineEdit, QComboBox, QDoubleSpinBox, QSizePolicy,
    )
    from PyQt6.QtCore import (
        Qt, QTimer, pyqtSignal, QThread,
        QPropertyAnimation, QVariantAnimation, QEasingCurve, QRectF,
    )
    from PyQt6.QtGui import (
        QAction, QIcon, QColor, QPalette, QFont, QPainter, QPen, QBrush,
    )
    PYQT6_AVAILABLE = True
except ImportError:
    PYQT6_AVAILABLE = False

import pyqtgraph as pg

from config import get_config
from core.state_db import StateDB
from trading.bridge_ccxt import CCXTBridge
from trading.bridge_mt5 import MT5Bridge

if not PYQT6_AVAILABLE:
    raise ImportError("PyQt6 is required. pip install PyQt6")

# Palette
BG="#11111b"; SURFACE="#1e1e2e"; SURFACE_HI="#28283c"; BORDER="#313244"
TEXT="#cdd6f4"; TEXT_DIM="#a6adc8"; TEXT_MUTE="#6c7086"
GREEN="#a6e3a1"; RED="#f38ba8"; GOLD="#f9e2af"; TEAL="#94e2d5"
MAUVE="#cba6f7"; YELLOW="#f5e0dc"; BLUE="#89b4fa"

pg.setConfigOptions(antialias=True, background=SURFACE, foreground=TEXT_DIM)

def fmt_amt(amt, cur):
    m = {"USD":"$","EUR":"\u20ac","GBP":"\u00a3","IDR":"Rp ","JPY":"\u00a5"}
    return f"{m.get(cur.upper(), cur+' ')}{amt:,.2f}" if cur else f"{amt:,.2f}"


# ═══ Ticker tape ═══
class _TickerTape(QWidget):
    def __init__(self, bridge, symbols, parent=None):
        super().__init__(parent)
        self._bridge = bridge; self._symbols = symbols
        self._offset = 0.0; self._quotes = {}; self._prev = {}
        self.setFixedHeight(36)
        self.setStyleSheet(f"background-color: {SURFACE}; border-bottom: 1px solid {BORDER};")
        t = QTimer(self); t.timeout.connect(self._refresh); t.start(2000)
        st = QTimer(self); st.timeout.connect(self.update); st.start(50)

    def _refresh(self):
        for sym in self._symbols:
            try:
                t = self._bridge.get_tick(sym)
                if t: self._quotes[sym] = (t.bid, t.ask)
            except Exception: pass
        self.update()

    def paintEvent(self, ev):
        from PyQt6.QtGui import QPainter
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(SURFACE))
        f = QFont("JetBrains Mono", 10); f.setBold(True); p.setFont(f)
        fm = p.fontMetrics(); x = -int(self._offset) % max(1, self.width())
        for sym, (bid, ask) in self._quotes.items():
            prev = self._prev.get(sym, bid)
            c = GREEN if bid >= prev else RED
            txt = f"  {sym}  {bid:.2f}  "
            w = fm.horizontalAdvance(txt) + 20
            p.setPen(QColor(c)); p.drawText(x, 23, txt)
            p.setPen(QColor(TEXT_MUTE))
            p.drawText(x + fm.horizontalAdvance(txt), 23, "\u25b2" if bid >= prev else "\u25bc")
            self._prev[sym] = bid; x += w
            if x > self.width(): break
        self._offset += 0.8
        p.end()


# ═══ Candlestick chart ═══
class _CandleChart(pg.GraphicsObject):
    """Custom candlestick renderer."""
    def __init__(self):
        super().__init__()
        self._candles = []
        self._w = 0.6
    def set_candles(self, candles):
        self._candles = candles; self.prepareGeometryChange()
    def boundingRect(self):
        if not self._candles: return QRectF()
        highs = [c['high'] for c in self._candles]
        lows = [c['low'] for c in self._candles]
        return QRectF(0, min(lows) * 0.999, len(self._candles), max(highs) * 1.001)
    def paint(self, p, *args):
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self._w
        for i, c in enumerate(self._candles):
            o, cl, h, l = c['open'], c['close'], c['high'], c['low']
            color = GREEN if cl >= o else RED
            pen = QPen(QColor(color), 0.8); p.setPen(pen)
            p.drawLine(int(i), int(l * 1000), int(i), int(h * 1000))
            body = QRectF(i - w/2, min(o, cl) * 1000, w, max(0.1, abs(cl - o) * 1000))
            brush = QBrush(QColor(color)); p.setBrush(brush)
            p.drawRect(body)


# ═══ Sparkline ═══
class _Sparkline(QWidget):
    def __init__(self, color=TEAL):
        super().__init__(); self._d = []; self._c = color; self.setFixedHeight(28)
    def set_data(self, vals):
        self._d = list(vals)[-40:]; self.update()
    def paintEvent(self, ev):
        from PyQt6.QtGui import QPainter
        if len(self._d) < 2: return
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        lo, hi = min(self._d), max(self._d); rng = (hi - lo) or 1.0
        w, h = self.width(), self.height()
        pts = [(i/(len(self._d)-1)*w, h-((v-lo)/rng)*(h-4)-2) for i, v in enumerate(self._d)]
        p.setPen(QPen(QColor(self._c), 1.5))
        for i in range(1, len(pts)):
            p.drawLine(int(pts[i-1][0]), int(pts[i-1][1]), int(pts[i][0]), int(pts[i][1]))
        p.end()


# ═══ KPI tile ═══
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
        self._cur = 0.0; self._anim = None; self._hist = []

    def animate_number(self, target, currency="USD"):
        if abs(target - self._cur) < 0.005:
            self._value_lbl.setText(fmt_amt(target, currency)); return
        start = self._cur; self._cur = target
        self._anim = QVariantAnimation(self)
        self._anim.setStartValue(start); self._anim.setEndValue(target)
        self._anim.setDuration(min(600, max(200, int(abs(target - start) / 50) + 200)))
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(lambda v: self._value_lbl.setText(fmt_amt(v, currency)))
        self._anim.start()

    def push_history(self, v):
        self._hist.append(v); self._hist = self._hist[-40:]; self._spark.set_data(self._hist)

    def set_text(self, text, color=TEXT):
        self._value_lbl.setText(text)
        self._value_lbl.setStyleSheet(f"color: {color}; font-size: 20px; font-weight: 700;")

    def flash(self, color):
        self._value_lbl.setStyleSheet(f"color: {color}; font-size: 20px; font-weight: 700;")
        QTimer.singleShot(400, lambda: self._value_lbl.setStyleSheet(f"color: {TEXT}; font-size: 20px; font-weight: 700;"))


# ═══ Order ticket ═══
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


# ═══ Card ═══
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


# ═══ Data worker ═══
class DataRefreshWorker(QThread):
    data_ready = pyqtSignal(dict)
    def __init__(self, bridge, symbols):
        super().__init__()
        self.bridge = bridge; self.symbols = symbols; self.running = True
    def run(self):
        while self.running:
            data = {'positions': [], 'daily_pl': 0.0, 'wins': 0, 'total': 0,
                    'balance': 0.0, 'currency': '', 'candles': [],
                    'ticker_quotes': {}, 'symbol_info': None}
            try:
                data['positions'] = self.bridge.get_positions()
                sym = self.symbols[0] if self.symbols else 'XAUUSD'
                data['daily_pl'], data['wins'], data['total'] = self.bridge.calculate_daily_pl(sym)
                data['candles'] = self.bridge.get_candles(sym, '15m', limit=120) or []
                if hasattr(self.bridge, 'get_balance'):
                    bal = self.bridge.get_balance()
                    data['balance'] = bal.get('equity', bal.get('balance', 0.0))
                    data['currency'] = bal.get('currency', 'USD')
                elif hasattr(self.bridge, '_exchange') and self.bridge._exchange:
                    bal = self.bridge._exchange.fetch_balance()
                    data['balance'] = bal.get('total', {}).get('USDT', 0.0)
                    data['currency'] = 'USDT'
                # fetch ticks for all symbols
                quotes = {}
                for sym in self.symbols:
                    try:
                        t = self.bridge.get_tick(sym)
                        if t: quotes[sym] = (t.bid, t.ask)
                    except Exception: pass
                data['ticker_quotes'] = quotes
                try:
                    info = self.bridge.get_symbol_info(sym)
                    if info: data['symbol_info'] = {'symbol': info.symbol, 'digits': info.digits, 'lot_min': info.lot_min}
                except Exception: pass
            except Exception: pass
            self.data_ready.emit(data)
            self.msleep(2000)
    def stop(self):
        self.running = False; self.wait()


# ═══ Main window ═══
class VilonaMainWindow(QMainWindow):
    def __init__(self, bridge, config, state_db):
        super().__init__()
        self.bridge = bridge; self.config = config; self.state_db = state_db
        self.symbols = config.trading.symbols or ['XAUUSD']
        self.running = False; self._currency = ''; self._pulse_state = False

        self.setWindowTitle("Vilona AI v2 \u2014 Trading Terminal")
        self.setGeometry(60, 40, 1560, 960)
        self._build_ui(); self._setup_tray(); self._apply_styles()

        for i, tile in enumerate([self.kpi_balance, self.kpi_equity, self.kpi_daily_pl,
                                   self.kpi_winrate, self.kpi_positions]):
            tile.setWindowOpacity(0.0); self._fade_in(tile, delay_ms=i * 100)

        self._pulse_timer = QTimer(self)
        self._pulse_timer.timeout.connect(self._pulse_dot)
        self._pulse_timer.start(900); self._pulse_state = False

        # Chart update timer
        self._chart_timer = QTimer(self)
        self._chart_timer.timeout.connect(self._update_chart)
        self._chart_timer.start(3000)

        self.refresh_worker = None; self._start_refresh()

    def _build_ui(self):
        central = QWidget(); self.setCentralWidget(central)
        root = QVBoxLayout(central); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)
        self.ticker = _TickerTape(self.bridge, self.symbols)
        root.addWidget(self.ticker)
        body = QWidget(); body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(14, 12, 14, 10); body_lay.setSpacing(12)
        root.addWidget(body, 1)
        # KPI row
        kpi_row = QHBoxLayout(); kpi_row.setSpacing(12)
        self.kpi_balance = _KpiTile("Account Balance", TEAL, TEAL)
        self.kpi_equity = _KpiTile("Equity", TEXT, BLUE)
        self.kpi_daily_pl = _KpiTile("Today's P/L", GREEN, GREEN)
        self.kpi_winrate = _KpiTile("Win Rate", MAUVE, MAUVE)
        self.kpi_positions = _KpiTile("Open Positions", YELLOW, YELLOW)
        self._kpi_tiles = [self.kpi_balance, self.kpi_equity, self.kpi_daily_pl,
                           self.kpi_winrate, self.kpi_positions]
        for k in self._kpi_tiles: kpi_row.addWidget(k, 1)
        body_lay.addLayout(kpi_row)
        # Main split
        hsplit = QHBoxLayout(); hsplit.setSpacing(12)
        # Left: chart + positions + log
        left = QVBoxLayout(); left.setSpacing(12)
        chart_card = _Card("")
        self.plot = pg.PlotWidget(); self.plot.setBackground(SURFACE)
        self.plot.showGrid(x=True, y=True, alpha=0.15)
        self.plot.getAxis('bottom').setPen(pg.mkPen(QColor(BORDER)))
        self.plot.getAxis('left').setPen(pg.mkPen(QColor(BORDER)))
        self.plot.getAxis('left').setLabel(f"{self.symbols[0] if self.symbols else 'XAUUSD'}", color=TEXT_DIM)
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
        # Right: order ticket, scanner, market info, log
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

    def _update_chart(self):
        try:
            sym = self.symbols[0] if self.symbols else 'XAUUSD'
            candles = self.bridge.get_candles(sym, '15m', limit=120) or []
            if not candles: return
            self.plot.clear()
            for i, c in enumerate(candles):
                o, cl, h, l = c['open'], c['close'], c['high'], c['low']
                color = GREEN if cl >= o else RED
                pen = pg.mkPen(QColor(color), width=0.8)
                self.plot.plot([i, i], [l * 1000, h * 1000], pen=pen)
                rect = pg.QtWidgets.QGraphicsRectItem(
                    QRectF(i - 0.35, min(o, cl) * 1000, 0.7, max(0.1, abs(cl - o) * 1000)))
                rect.setPen(pen); rect.setBrush(pg.mkBrush(QColor(color)))
                self.plot.addItem(rect)
            self.plot.setTitle(f"<span style='color:{TEXT_DIM};font-size:11pt'>"
                              f"{sym} M15 last={candles[-1]['close']:.2f}</span>")
        except Exception as e:
            pass

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
        if 'ticker_quotes' in data and data['ticker_quotes']:
            self.ticker._quotes = data['ticker_quotes']
        try:
            info = data.get('symbol_info')
            if info: self._symbol_info_label.setText(f"{info['symbol']} digits={info['digits']} lot_min={info['lot_min']}")
        except Exception: pass
        if self.bridge.is_connected():
            self.status_dot.setText("\u25cf Connected")
            self.status_dot.setStyleSheet(f"color: {GREEN}; font-size: 15px; font-weight: 700;")
        else:
            self.status_dot.setText("\u25cf Disconnected")
            self.status_dot.setStyleSheet(f"color: {RED}; font-size: 15px; font-weight: 700;")

    def _submit_order(self, side, symbol, lot, sl, tp):
        self._log(f"Order: {side.upper()} {symbol} {lot} SL={sl} TP={tp}")
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

def main():
    app = QApplication(sys.argv); app.setStyle('Fusion')
    cfg = get_config(); state_db = StateDB()
    bridge = MT5Bridge() if cfg.exchange.name.lower() == 'mt5' else CCXTBridge(cfg.exchange)
    if not bridge.connect():
        print("Failed to connect to exchange"); return 1
    if cfg.exchange.name.lower() == 'mt5':
        cfg.trading.symbols = bridge.get_available_symbols()
    window = VilonaMainWindow(bridge, cfg, state_db); window.show()
    return app.exec()

if __name__ == "__main__":
    sys.exit(main())
