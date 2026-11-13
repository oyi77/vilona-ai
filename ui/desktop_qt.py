"""Vilona AI v2 - Qt Desktop UI (PyQt6)

Trading control panel with a dark trading-desk design: card layout,
currency-aware balance display, KPI tiles, positions table, and scanner
controls. Palette: Catppuccin Mocha-inspired with teal/gold accents.
"""
from __future__ import annotations

import sys
from datetime import datetime

try:
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QPushButton, QLabel, QTableWidget, QTableWidgetItem, QHeaderView,
        QFrame, QGridLayout, QSplitter, QTextEdit, QStatusBar,
        QSystemTrayIcon, QMenu, QStyle, QMessageBox,
    )
    from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread
    from PyQt6.QtGui import QAction, QIcon, QColor, QPalette, QFont
    PYQT6_AVAILABLE = True
except ImportError:
    PYQT6_AVAILABLE = False

from config import get_config
from core.state_db import StateDB
from trading.bridge_ccxt import CCXTBridge
from trading.bridge_mt5 import MT5Bridge


if not PYQT6_AVAILABLE:
    raise ImportError("PyQt6 is required for the desktop UI. Install with: pip install PyQt6")

# ── Palette ──────────────────────────────────────────────────────────────────
BG          = "#11111b"
SURFACE     = "#1e1e2e"
SURFACE_HI  = "#28283c"
BORDER      = "#313244"
TEXT        = "#cdd6f4"
TEXT_DIM    = "#a6adc8"
TEXT_MUTE   = "#6c7086"
GREEN       = "#a6e3a1"
RED         = "#f38ba8"
GOLD        = "#f9e2af"
TEAL        = "#94e2d5"
MAUVE       = "#cba6f7"
YELLOW      = "#f5e0dc"  # peach


def _fmt_amount(amount: float, currency: str) -> str:
    """Currency-aware formatter."""
    if not currency:
        return f"{amount:,.2f}"
    symbols = {"USD": "$", "EUR": "€", "GBP": "£", "IDR": "Rp ", "JPY": "¥"}
    sym = symbols.get(currency.upper(), f"{currency.upper()} ")
    return f"{sym}{amount:,.2f}"


class _Card(QFrame):
    """Flat card with subtle border."""
    def __init__(self, title: str = "", parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            f"background-color: {SURFACE}; border: 1px solid {BORDER};"
            "border-radius: 10px;"
        )
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(16, 14, 16, 14)
        self._layout.setSpacing(10)
        if title:
            lbl = QLabel(title)
            lbl.setStyleSheet(f"color: {TEXT_DIM}; font-size: 11px; letter-spacing: 1px;"
                              "font-weight: 600; text-transform: uppercase;")
            self._layout.addWidget(lbl)


class _KpiTile(QFrame):
    """Large KPI number in a card."""
    def __init__(self, title: str, value: str = "—", color: str = TEXT, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            f"background-color: {SURFACE}; border: 1px solid {BORDER};"
            "border-radius: 10px;"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(4)
        self._title = title
        t_lbl = QLabel(title.upper())
        t_lbl.setStyleSheet(f"color: {TEXT_MUTE}; font-size: 10px; letter-spacing: 1px;"
                            "font-weight: 600;")
        lay.addWidget(t_lbl)
        self._value_lbl = QLabel(value)
        self._value_lbl.setStyleSheet(f"color: {color}; font-size: 22px; font-weight: 700;")
        lay.addWidget(self._value_lbl)

    def set_value(self, value: str, color: str = TEXT):
        self._value_lbl.setText(value)
        self._value_lbl.setStyleSheet(f"color: {color}; font-size: 22px; font-weight: 700;")


class DataRefreshWorker(QThread):
    """Background worker polling bridge every 2 s."""
    data_ready = pyqtSignal(dict)

    def __init__(self, bridge, symbols):
        super().__init__()
        self.bridge = bridge
        self.symbols = symbols
        self.running = True

    def run(self):
        while self.running:
            data = {
                'positions': [],
                'daily_pl': 0.0,
                'wins': 0,
                'total': 0,
                'balance': 0.0,
                'currency': '',
            }
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
            self.msleep(2000)

    def stop(self):
        self.running = False
        self.wait()


class VilonaMainWindow(QMainWindow):
    def __init__(self, bridge, config, state_db):
        super().__init__()
        self.bridge = bridge
        self.config = config
        self.state_db = state_db
        self.symbols = config.trading.symbols
        self.running = False
        self._currency = ''

        self.setWindowTitle("Vilona AI v2 — Trading Desk")
        self.setGeometry(80, 60, 1440, 900)
        self._build_ui()
        self._setup_tray()
        self._apply_styles()

        self.refresh_worker = None
        self._start_refresh()

    # ── UI build ──────────────────────────────────────────────────────────────
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(14)

        # ── KPI row ───────────────────────────────────────────────────────────
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(14)
        self.kpi_balance  = _KpiTile("Account Balance", "—", TEAL)
        self.kpi_equity   = _KpiTile("Equity", "—", TEXT)
        self.kpi_daily_pl = _KpiTile("Today's P/L", "—", GREEN)
        self.kpi_winrate  = _KpiTile("Win Rate", "—", MAUVE)
        self.kpi_positions = _KpiTile("Open Positions", "—", YELLOW)
        for k in (self.kpi_balance, self.kpi_equity, self.kpi_daily_pl,
                  self.kpi_winrate, self.kpi_positions):
            kpi_row.addWidget(k, 1)
        root.addLayout(kpi_row)

        # ── Main split: left (positions + logs) | right (controls) ────────────
        hsplit = QHBoxLayout()
        hsplit.setSpacing(14)

        # Left: positions table + logs
        left = QVBoxLayout()
        left.setSpacing(14)

        pos_card = _Card("Open Positions")
        self.pos_table = QTableWidget()
        self.pos_table.setColumnCount(9)
        self.pos_table.setHorizontalHeaderLabels([
            "Ticket", "Symbol", "Type", "Volume", "Entry",
            "Current", "SL", "TP", "P/L",
        ])
        hdr = self.pos_table.horizontalHeader()
        for i in range(9):
            hdr.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.pos_table.setAlternatingRowColors(True)
        self.pos_table.verticalHeader().setVisible(False)
        self.pos_table.setShowGrid(False)
        self.pos_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        pos_card._layout.addWidget(self.pos_table)
        left.addWidget(pos_card, 3)

        log_card = _Card("System Log")
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 9))
        self.log_text.setMinimumHeight(140)
        log_card._layout.addWidget(self.log_text)
        left.addWidget(log_card, 1)

        hsplit.addLayout(left, 3)

        # Right: scanner + controls
        right = QVBoxLayout()
        right.setSpacing(14)

        scanner_card = _Card("Scanner")
        scanner_lay = scanner_card._layout
        self.status_dot = QLabel("● Disconnected")
        self.status_dot.setStyleSheet(f"color: {RED}; font-size: 15px; font-weight: 700;")
        scanner_lay.addWidget(self.status_dot)

        self._symbol_label = QLabel(f"Symbol: {', '.join(self.symbols)}")
        self._symbol_label.setStyleSheet(f"color: {TEXT_DIM}; font-size: 12px;")
        scanner_lay.addWidget(self._symbol_label)

        spacer = QWidget(); spacer.setFixedHeight(12)
        scanner_lay.addWidget(spacer)

        self.btn_start = QPushButton("▶  Start Scanner")
        self.btn_start.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_start.clicked.connect(self.start_scanner)
        scanner_lay.addWidget(self.btn_start)

        self.btn_stop = QPushButton("⏹  Stop Scanner")
        self.btn_stop.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_stop.clicked.connect(self.stop_scanner)
        self.btn_stop.setEnabled(False)
        scanner_lay.addWidget(self.btn_stop)

        self.btn_close_all = QPushButton("⚠  Close All Positions")
        self.btn_close_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close_all.clicked.connect(self.close_all)
        scanner_lay.addWidget(self.btn_close_all)

        right.addWidget(scanner_card)

        # Symbol info card
        info_card = _Card("Market Info")
        self._symbol_info_label = QLabel("—")
        self._symbol_info_label.setWordWrap(True)
        self._symbol_info_label.setStyleSheet(f"color: {TEXT_DIM}; font-size: 11px;")
        info_card._layout.addWidget(self._symbol_info_label)
        right.addWidget(info_card)

        right.addStretch(1)
        hsplit.addLayout(right, 1)

        root.addLayout(hsplit, 1)

        # Status bar
        self.statusBar().showMessage("Ready")

    # ── Tray ──────────────────────────────────────────────────────────────────
    def _setup_tray(self):
        self.tray = QSystemTrayIcon(self)
        icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        self.tray.setIcon(icon)
        self.tray.setVisible(True)
        tray_menu = QMenu()
        show_action = QAction("Show", self);  show_action.triggered.connect(self.show)
        hide_action = QAction("Hide", self);  hide_action.triggered.connect(self.hide)
        quit_action = QAction("Quit", self);  quit_action.triggered.connect(self.close)
        tray_menu.addAction(show_action)
        tray_menu.addAction(hide_action)
        tray_menu.addSeparator()
        tray_menu.addAction(quit_action)
        self.tray.setContextMenu(tray_menu)

    # ── Stylesheet ────────────────────────────────────────────────────────────
    def _apply_styles(self):
        self.setStyleSheet(f"""
            QMainWindow {{ background-color: {BG}; }}
            QGroupBox {{
                color: {TEXT_DIM};
                font-weight: 600;
                border: 1px solid {BORDER};
                border-radius: 10px;
                margin-top: 10px;
                padding-top: 10px;
            }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 4px; }}
            QTableWidget {{
                background-color: {SURFACE};
                alternate-background-color: {SURFACE_HI};
                color: {TEXT};
                gridline-color: {BORDER};
                border: none;
                border-radius: 6px;
                selection-background-color: {MAUVE};
                selection-color: {BG};
            }}
            QHeaderView::section {{
                background-color: {SURFACE_HI};
                color: {TEXT_MUTE};
                padding: 7px 6px;
                font-weight: 600;
                font-size: 10px;
                border: none;
                border-bottom: 1px solid {BORDER};
            }}
            QPushButton {{
                border: none;
                border-radius: 8px;
                padding: 12px 18px;
                font-size: 13px;
                font-weight: 600;
                color: {BG};
            }}
            QPushButton:disabled {{ opacity: 0.4; }}
            QTextEdit {{
                background-color: {SURFACE};
                color: {TEXT};
                border: none;
                border-radius: 6px;
                font-family: 'JetBrains Mono', 'Consolas', monospace;
                font-size: 11px;
            }}
            QLabel {{ color: {TEXT}; }}
            QStatusBar {{ background-color: {SURFACE}; color: {TEXT_MUTE}; }}
            QScrollBar::vertical {{
                background: {SURFACE_HI}; width: 6px; border-radius: 3px;
            }}
            QScrollBar::handle:vertical {{
                background: {BORDER}; border-radius: 3px; min-height: 30px;
            }}
        """)

        # Per-button accent colors
        self.btn_start.setStyleSheet(
            f"background-color: {GREEN}; color: {BG}; padding: 12px 18px;"
            "border-radius: 8px; font-weight: 700; font-size: 13px;"
        )
        self.btn_stop.setStyleSheet(
            f"background-color: {RED}; color: {BG}; padding: 12px 18px;"
            "border-radius: 8px; font-weight: 700; font-size: 13px;"
        )
        self.btn_close_all.setStyleSheet(
            f"background-color: {YELLOW}; color: {BG}; padding: 12px 18px;"
            "border-radius: 8px; font-weight: 700; font-size: 13px;"
        )
        self.btn_stop.setEnabled(False)
        self.btn_stop.setStyleSheet(
            f"background-color: {BORDER}; color: {TEXT_MUTE}; padding: 12px 18px;"
            "border-radius: 8px; font-weight: 700; font-size: 13px;"
        )

    # ── Refresh ───────────────────────────────────────────────────────────────
    def _start_refresh(self):
        self.refresh_worker = DataRefreshWorker(self.bridge, self.symbols)
        self.refresh_worker.data_ready.connect(self._on_data)
        self.refresh_worker.start()
        self._log("Data refresh started")

    def _on_data(self, data):
        positions = data.get('positions', [])
        currency = data.get('currency', 'USD') or 'USD'
        self._currency = currency

        # KPIs
        bal = data.get('balance', 0.0)
        self.kpi_balance.set_value(_fmt_amount(bal, currency), TEAL)
        self.kpi_equity.set_value(_fmt_amount(bal, currency), TEXT)

        pl = data.get('daily_pl', 0.0)
        pl_color = GREEN if pl >= 0 else RED
        pl_prefix = "+" if pl > 0 else ""
        self.kpi_daily_pl.set_value(_fmt_amount(pl, currency), pl_color)

        wins = data.get('wins', 0)
        total = data.get('total', 0)
        wr = wins / total * 100 if total else 0.0
        self.kpi_winrate.set_value(f"{wr:.1f}%  ({wins}/{total})", MAUVE)
        self.kpi_positions.set_value(str(len(positions)), YELLOW)

        # Positions table
        self.pos_table.setRowCount(len(positions))
        for row, pos in enumerate(positions):
            self.pos_table.setItem(row, 0, QTableWidgetItem(str(pos.ticket)))
            self.pos_table.setItem(row, 1, QTableWidgetItem(pos.symbol))
            self.pos_table.setItem(row, 2, QTableWidgetItem(pos.type.upper()))
            self.pos_table.setItem(row, 3, QTableWidgetItem(f"{pos.volume:.4f}"))
            self.pos_table.setItem(row, 4, QTableWidgetItem(f"{pos.price_open:.{5}f}"))
            self.pos_table.setItem(row, 5, QTableWidgetItem(f"{pos.price_current:.{5}f}"))
            self.pos_table.setItem(row, 6, QTableWidgetItem(f"{pos.sl:.{5}f}" if pos.sl else "—"))
            self.pos_table.setItem(row, 7, QTableWidgetItem(f"{pos.tp:.{5}f}" if pos.tp else "—"))
            profit = pos.profit
            color_hex = GREEN if profit >= 0 else RED
            item = QTableWidgetItem(f"{'+' if profit > 0 else ''}{profit:.2f}")
            item.setForeground(QColor(color_hex))
            self.pos_table.setItem(row, 8, item)

        # Connection dot
        connected = self.bridge.is_connected()
        if connected:
            self.status_dot.setText("● Connected")
            self.status_dot.setStyleSheet(f"color: {GREEN}; font-size: 15px; font-weight: 700;")
        else:
            self.status_dot.setText("● Disconnected")
            self.status_dot.setStyleSheet(f"color: {RED}; font-size: 15px; font-weight: 700;")

    # ── Scanner controls ───────────────────────────────────────────────────────
    def start_scanner(self):
        self.running = True
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.btn_stop.setStyleSheet(
            f"background-color: {RED}; color: {BG}; padding: 12px 18px;"
            "border-radius: 8px; font-weight: 700; font-size: 13px;"
        )
        self._log("Scanner started")

    def stop_scanner(self):
        self.running = False
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.btn_stop.setStyleSheet(
            f"background-color: {BORDER}; color: {TEXT_MUTE}; padding: 12px 18px;"
            "border-radius: 8px; font-weight: 700; font-size: 13px;"
        )
        self._log("Scanner stopped")

    def close_all(self):
        reply = QMessageBox.question(
            self, 'Confirm Close All',
            f"Close all {self.bridge.get_positions().__len__()} positions?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                positions = self.bridge.get_positions()
                for pos in positions:
                    self.bridge.close_position(pos.ticket, pos.symbol)
                self._log(f"Closed {len(positions)} positions")
            except Exception as e:
                self._log(f"Error closing positions: {e}")

    def _log(self, message: str):
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
    if cfg.exchange.name.lower() == 'mt5':
        bridge = MT5Bridge()
    else:
        bridge = CCXTBridge(cfg.exchange)
    if not bridge.connect():
        print("Failed to connect to exchange")
        return 1
    window = VilonaMainWindow(bridge, cfg, state_db)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())