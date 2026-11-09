"""Vilona AI v2 - Qt Desktop UI (PyQt6)

Professional desktop control panel with real-time P/L, position management,
scanner control, and Telegram integration.
"""

import sys

try:
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QPushButton, QLabel, QTableWidget, QTableWidgetItem, QHeaderView,
        QGroupBox, QGridLayout, QSplitter, QTextEdit, QStatusBar,
        QSystemTrayIcon, QMenu, QStyle, QMessageBox
    )
    from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread
    from PyQt6.QtGui import QAction, QIcon, QColor, QPalette
    PYQT6_AVAILABLE = True
except ImportError:
    PYQT6_AVAILABLE = False

from config import get_config
from core.state_db import StateDB
from trading.bridge_ccxt import CCXTBridge
from trading.bridge_mt5 import MT5Bridge


if not PYQT6_AVAILABLE:
    raise ImportError("PyQt6 is required for the desktop UI. Install with: pip install PyQt6")

class DataRefreshWorker(QThread):
    """Background worker for data refresh"""
    data_ready = pyqtSignal(dict)

    def __init__(self, bridge, state_db, symbols):
        super().__init__()
        self.bridge = bridge
        self.state_db = state_db
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
            }
            try:
                positions = self.bridge.get_positions()
                data['positions'] = positions
                pl, wins, total = self.bridge.calculate_daily_pl(self.symbols[0] if self.symbols else 'BTC/USDT')
                data['daily_pl'] = pl
                data['wins'] = wins
                data['total'] = total
                if hasattr(self.bridge, '_exchange') and self.bridge._exchange:
                    bal = self.bridge._exchange.fetch_balance()
                    data['balance'] = bal.get('total', {}).get('USDT', 0.0)
            except Exception as e:
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

        self.setWindowTitle("Vilona AI v2 - Desktop Control")
        self.setGeometry(100, 100, 1400, 900)
        self.setup_ui()
        self.setup_tray()
        self.setup_styles()

        self.refresh_worker = None
        self.start_refresh()

    def setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        # Header
        header = QGroupBox("Vilona AI v2 - Trading Control Panel")
        header_layout = QHBoxLayout(header)
        self.status_label = QLabel("● Disconnected")
        self.status_label.setStyleSheet("color: #ff5555; font-weight: bold; font-size: 14px;")
        header_layout.addWidget(self.status_label)
        header_layout.addStretch()
        self.balance_label = QLabel("Balance: $0.00")
        self.balance_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        header_layout.addWidget(self.balance_label)
        main_layout.addWidget(header)

        # Splitter
        splitter = QSplitter(Qt.Orientation.Vertical)

        # Positions Table
        pos_group = QGroupBox("Open Positions")
        pos_layout = QVBoxLayout(pos_group)
        self.pos_table = QTableWidget()
        self.pos_table.setColumnCount(9)
        self.pos_table.setHorizontalHeaderLabels([
            "Ticket", "Symbol", "Type", "Volume", "Entry Price",
            "Current Price", "SL", "TP", "P/L"
        ])
        self.pos_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.pos_table.setAlternatingRowColors(True)
        pos_layout.addWidget(self.pos_table)
        splitter.addWidget(pos_group)

        # Control Panel
        ctrl_group = QGroupBox("Scanner Control")
        ctrl_layout = QHBoxLayout(ctrl_group)

        self.btn_start = QPushButton("▶ Start Scanner")
        self.btn_start.setStyleSheet("background-color: #28a745; color: white; padding: 12px; font-weight: bold;")
        self.btn_start.clicked.connect(self.start_scanner)
        ctrl_layout.addWidget(self.btn_start)

        self.btn_stop = QPushButton("⏹ Stop Scanner")
        self.btn_stop.setStyleSheet("background-color: #dc3545; color: white; padding: 12px; font-weight: bold;")
        self.btn_stop.clicked.connect(self.stop_scanner)
        self.btn_stop.setEnabled(False)
        ctrl_layout.addWidget(self.btn_stop)

        self.btn_close_all = QPushButton("⚠ Close All")
        self.btn_close_all.setStyleSheet("background-color: #ffc107; color: black; padding: 12px; font-weight: bold;")
        self.btn_close_all.clicked.connect(self.close_all)
        ctrl_layout.addWidget(self.btn_close_all)

        ctrl_layout.addStretch()

        # Daily Stats
        stats_group = QGroupBox("Today's Performance")
        stats_layout = QHBoxLayout(stats_group)
        self.daily_pl_label = QLabel("P/L: $0.00")
        self.daily_pl_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        stats_layout.addWidget(self.daily_pl_label)
        stats_layout.addStretch()
        self.winrate_label = QLabel("Win Rate: 0%")
        self.winrate_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        stats_layout.addWidget(self.winrate_label)
        ctrl_layout.addWidget(stats_group)

        splitter.addWidget(ctrl_group)

        # Logs
        log_group = QGroupBox("System Logs")
        log_layout = QVBoxLayout(log_group)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(200)
        log_layout.addWidget(self.log_text)
        splitter.addWidget(log_group)

        splitter.setSizes([500, 150, 250])
        main_layout.addWidget(splitter)

        # Status Bar
        self.statusBar().showMessage("Ready")

    def setup_tray(self):
        self.tray = QSystemTrayIcon(self)
        icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        self.tray.setIcon(icon)
        self.tray.setVisible(True)

        tray_menu = QMenu()
        show_action = QAction("Show", self)
        show_action.triggered.connect(self.show)
        tray_menu.addAction(show_action)

        hide_action = QAction("Hide", self)
        hide_action.triggered.connect(self.hide)
        tray_menu.addAction(hide_action)

        tray_menu.addSeparator()

        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.close)
        tray_menu.addAction(quit_action)

        self.tray.setContextMenu(tray_menu)

    def setup_styles(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1e1e2e;
            }
            QGroupBox {
                color: #cdd6f4;
                font-weight: bold;
                border: 2px solid #45475a;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
            QTableWidget {
                background-color: #313244;
                color: #cdd6f4;
                gridline-color: #45475a;
                border: none;
            }
            QTableWidget::item:selected {
                background-color: #585b70;
            }
            QHeaderView::section {
                background-color: #45475a;
                color: #cdd6f4;
                padding: 8px;
                font-weight: bold;
                border: none;
            }
            QPushButton {
                border: none;
                border-radius: 6px;
                padding: 10px 20px;
                font-size: 13px;
            }
            QPushButton:hover {
                opacity: 0.9;
            }
            QTextEdit {
                background-color: #313244;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 6px;
                font-family: 'Consolas', monospace;
            }
            QLabel {
                color: #cdd6f4;
            }
        """)

    def start_refresh(self):
        self.refresh_worker = DataRefreshWorker(self.bridge, self.state_db, self.symbols)
        self.refresh_worker.data_ready.connect(self.update_ui)
        self.refresh_worker.start()
        self.log("Data refresh started")

    def update_ui(self, data):
        # Update positions
        positions = data.get('positions', [])
        self.pos_table.setRowCount(len(positions))
        for row, pos in enumerate(positions):
            self.pos_table.setItem(row, 0, QTableWidgetItem(str(pos.ticket)))
            self.pos_table.setItem(row, 1, QTableWidgetItem(pos.symbol))
            self.pos_table.setItem(row, 2, QTableWidgetItem(pos.type.upper()))
            self.pos_table.setItem(row, 3, QTableWidgetItem(f"{pos.volume:.4f}"))
            self.pos_table.setItem(row, 4, QTableWidgetItem(f"{pos.price_open:.5f}"))
            self.pos_table.setItem(row, 5, QTableWidgetItem(f"{pos.price_current:.5f}"))
            self.pos_table.setItem(row, 6, QTableWidgetItem(f"{pos.sl:.5f}" if pos.sl else "0"))
            self.pos_table.setItem(row, 7, QTableWidgetItem(f"{pos.tp:.5f}" if pos.tp else "0"))

            pl_item = QTableWidgetItem(f"${pos.profit:.2f}")
            if pos.profit > 0:
                pl_item.setForeground(QColor("#26a69a"))
            elif pos.profit < 0:
                pl_item.setForeground(QColor("#ef5350"))
            self.pos_table.setItem(row, 8, pl_item)

        # Update stats
        self.daily_pl_label.setText(f"P/L: ${data.get('daily_pl', 0.0):.2f}")
        wins = data.get('wins', 0)
        total = data.get('total', 0)
        winrate = (wins / total * 100) if total > 0 else 0
        self.winrate_label.setText(f"Win Rate: {winrate:.1f}% ({wins}/{total})")
        self.balance_label.setText(f"Balance: ${data.get('balance', 0.0):.2f}")

        # Update connection status
        if self.bridge.is_connected():
            self.status_label.setText("● Connected")
            self.status_label.setStyleSheet("color: #26a69a; font-weight: bold; font-size: 14px;")

    def start_scanner(self):
        self.running = True
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.log("Scanner started")

    def stop_scanner(self):
        self.running = False
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.log("Scanner stopped")

    def close_all(self):
        reply = QMessageBox.question(
            self, 'Confirm Close All',
            'Are you sure you want to close all positions?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                positions = self.bridge.get_positions()
                for pos in positions:
                    self.bridge.close_position(pos.ticket, pos.symbol)
                self.log(f"Closed {len(positions)} positions")
            except Exception as e:
                self.log(f"Error closing positions: {e}")

    def log(self, message):
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {message}")

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
        print(f"Failed to connect to exchange")
        return 1

    window = VilonaMainWindow(bridge, cfg, state_db)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())