# File: chrome.pyc (Python 3.10)

"""
chrome.py
=========
Perlengkapan bingkai shell KingAI (pola QueenAI: sidebar + status bar):

    NavRail    sidebar kiri - "rel" ikon saat jendela ramping (450 px), melebar
               dengan label saat jendela lebar / maximize. Item aktif = pelat
               berlian merah bercahaya + bilah emas.
    StatusBar  strip bawah: koneksi MT5, model AI, simbol, jam server lokal.
    Toast      notifikasi singkat di dalam jendela (bukan popup OS).
"""

from __future__ import annotations
import math
from core.i18n import tr
from core.qt import (
    QAbstractButton,
    QColor,
    QEasingCurve,
    QFontMetricsF,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPointF,
    QPropertyAnimation,
    QRadialGradient,
    QRectF,
    QSize,
    QSizePolicy,
    QTimer,
    QVBoxLayout,
    QWidget,
    Qt,
    Signal,
)
from ui.kingai_theme import fx
from ui import assets
from ui.kingai_theme import theme
from ui.kingai_theme.widgets import Chip

COMPACT_W = 62
EXPANDED_W = 188


class _NavItem(QAbstractButton):
    def __init__(self, key=None, icon=None, parent=None):
        super().__init__(parent)
        self.key = key
        self.icon_name = icon
        self.label = ''
        self.compact = True
        self.active = False
        self._hover = 0
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(50)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def enterEvent(self, e):
        self._hover = 1
        self.update()

    def leaveEvent(self, e):
        self._hover = 0
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        h = self.height()
        cx = COMPACT_W / 2
        cy = h / 2
        if self.active or self._hover:
            plate = QPainterPath()
            s = 17 if self.active else 15
            plate.moveTo(cx, cy - s)
            plate.lineTo(cx + s, cy)
            plate.lineTo(cx, cy + s)
            plate.lineTo(cx - s, cy)
            plate.closeSubpath()
            if self.active:
                halo = QRadialGradient(cx, cy, 30)
                halo.setColorAt(0, theme.qc(theme.RED, 0.45))
                halo.setColorAt(1, theme.qc(theme.RED, 0))
                p.setPen(Qt.NoPen)
                p.setBrush(halo)
                p.drawEllipse(QPointF(cx, cy), 30, 30)
                g = QLinearGradient(cx, cy - s, cx, cy + s)
                g.setColorAt(0, QColor('#c3122e'))
                g.setColorAt(1, QColor('#45040e'))
                p.fillPath(plate, g)
                fx.glow_stroke(p, plate, theme.qc(theme.RED_HOT, 0.95), 1.2, 7, 4, 1)
            else:
                p.fillPath(plate, theme.qc('#2a0e15', 0.9))
                p.strokePath(plate, QPen(theme.qc(theme.LINE_HI, 1), 1))
        if self.active:
            bar = QLinearGradient(0, cy - 16, 0, cy + 16)
            bar.setColorAt(0, theme.qc(theme.GOLD, 0))
            bar.setColorAt(0.5, QColor(theme.GOLD))
            bar.setColorAt(1, theme.qc(theme.GOLD, 0))
            p.fillRect(QRectF(0, cy - 16, 2.5, 32), bar)
        if self.active:
            pass
        elif self._hover:
            pass

        color = theme.TEXT_DIM
        pm = assets.icon_pixmap(self.icon_name, color, 18)
        p.drawPixmap(QPointF(cx - 9, cy - 9), pm)
        if not self.compact:
            p.setFont(theme.font(9.5, spacing=1.6))
            p.setPen(QColor(theme.GOLD_HI if self.active else theme.TEXT_DIM))
            p.drawText(
                QRectF(COMPACT_W - 4, 0, self.width() - COMPACT_W, h),
                Qt.AlignVCenter | Qt.AlignLeft,
                self.label.upper(),
            )
        p.end()


class _RunBeacon(QWidget):
    """Mercusuar kecil di dasar sidebar: mahkota berdenyut saat Auto Trade jalan."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.running = False
        self.compact = True
        self.text = ''
        self._t = 0
        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._tick)
        self.setFixedHeight(54)

    def set_running(self, running=None, text=None):
        self.running = running
        self.text = text
        if running:
            self._timer.start()
        else:
            self._timer.stop()
            self.update()
            return None
        self.update()

    def _tick(self):
        self._t += 0.05
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        cx = COMPACT_W / 2
        cy = self.height() / 2
        color = theme.GREEN if self.running else theme.TEXT_MUTE
        pulse = 0.5 + 0.5 * math.sin(self._t * 4) if self.running else 0
        if self.running:
            for k in range(2):
                ph = (self._t * 0.8 + k * 0.5) % 1
                p.setPen(QPen(theme.qc(theme.GREEN, 0.6 * (1 - ph)), 1.4))
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(QPointF(cx, cy), 10 + 14 * ph, 10 + 14 * ph)
        p.setPen(QPen(theme.qc(color, 0.8 if self.running else 0.5), 1.2))
        p.setBrush(theme.qc('#050204', 0.9))
        p.drawEllipse(QPointF(cx, cy), 13, 13)
        pm = assets.icon_pixmap(
            'crown', fx.lerp_color(color, '#ffffff', pulse * 0.4).name(), 14
        )
        p.drawPixmap(QPointF(cx - 7, cy - 7.5), pm)
        if not self.compact:
            p.setFont(theme.font(8, spacing=1.2))
            p.setPen(QColor(color))
            p.drawText(
                QRectF(COMPACT_W - 4, 0, self.width() - COMPACT_W, self.height()),
                Qt.AlignVCenter | Qt.AlignLeft,
                self.text.upper(),
            )
        p.end()


class NavRail(QWidget):
    navigate = Signal(str)
    ITEMS = (
        ('dashboard', 'crown', 'king.nav_dashboard'),
        ('news', 'scroll', 'king.nav_news'),
        ('history', 'ledger', 'king.nav_history'),
        ('tokens', 'coin', 'king.nav_tokens'),
        ('settings', 'gear', 'king.nav_settings'),
        ('about', 'info', 'king.nav_about'),
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self.compact = True
        self.setFixedWidth(COMPACT_W)
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 10, 0, 6)
        col.setSpacing(4)
        self.items = {}
        for key, icon, _label in self.ITEMS:
            item = _NavItem(key, icon)
            item.clicked.connect(lambda _checked=False, k=key: self.navigate.emit(k))
            col.addWidget(item)
            self.items[key] = item
        col.addStretch(1)
        self.beacon = _RunBeacon()
        col.addWidget(self.beacon)
        self.retranslate()

    def retranslate(self):
        for key, _icon, label_key in self.ITEMS:
            self.items[key].label = tr(label_key)
            self.items[key].setToolTip(tr(label_key))
            self.items[key].update()

    def select(self, key=None):
        for k, item in self.items.items():
            item.active = k == key
            item.update()

    def set_compact(self, compact=None):
        if compact == self.compact:
            return None
        self.compact = compact
        self.setFixedWidth(COMPACT_W if compact else EXPANDED_W)
        for item in self.items.values():
            item.compact = compact
            item.update()
        self.beacon.compact = compact
        self.beacon.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = self.width()
        h = self.height()
        g = QLinearGradient(0, 0, w, 0)
        g.setColorAt(0, QColor('#0b0507'))
        g.setColorAt(1, QColor('#070304'))
        p.fillRect(self.rect(), g)
        x = w - 0.5
        line = QLinearGradient(x, 0, x, h)
        line.setColorAt(0, theme.qc(theme.RED, 0.55))
        line.setColorAt(0.5, theme.qc(theme.RED_DEEP, 0.35))
        line.setColorAt(1, theme.qc(theme.GOLD, 0.25))
        p.setPen(QPen(line, 1))
        p
