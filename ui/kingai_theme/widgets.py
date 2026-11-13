"""\nwidgets.py\n==========\nPerangkat widget KingAI - semuanya digambar sendiri (QPainter), bukan QSS:\n\n    HudPanel / HudCard   panel bertakik bercahaya (+ header ikon & judul)\n    KButton              tombol bertakik: primary / gold / ghost / danger / success\n    IconButton           tombol ikon persegi (title bar, aksi kecil)\n    CommandButton        tombol raksasa START / STOP AUTOTRADE (denyut + kilau)\n    KSwitch              saklar geser beranimasi\n    Segmented            pilihan bersegmen\n    Chip                 label status kecil bertakik\n    StatTile             angka besar beranimasi (kartu akun)\n    RingGauge            cincin persentase (win rate)\n    ModelPicker          combo model yang bisa diketik & disaring\n    NumberEdit           input angka tanpa tombol panah\n"""

from __future__ import annotations
import math
from core.i18n import tr
from core.qt import (
    QAbstractButton,
    QColor,
    QComboBox,
    QCompleter,
    QDoubleSpinBox,
    QEasingCurve,
    QFont,
    QFontMetricsF,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPointF,
    QRadialGradient,
    QRectF,
    QSize,
    QSizePolicy,
    QTimer,
    QVariantAnimation,
    QVBoxLayout,
    QWidget,
    Qt,
    Signal,
)
from ui.kingai_theme import fx, theme
from ui import assets


def caps(
    text: str,
    size: float = 8.5,
    color: str = theme.TEXT_DIM,
    spacing: float = 1.4,
    bold: bool = True,
) -> QLabel:
    """Label huruf kapital berjarak - judul seksi, label statistik."""
    lbl = QLabel(text.upper())
    lbl.setFont(theme.font(size, display=True, spacing=spacing))
    lbl.setStyleSheet(f'color: {color};')
    return lbl


def note(text: str = '', wrap: bool = True) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName('Note')
    lbl.setWordWrap(wrap)
    return lbl


def field_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName('FieldLabel')
    return lbl


def hbox(*items, spacing: int = 8, margins=(0, 0, 0, 0)) -> QHBoxLayout:
    """None = stretch."""
    lay = QHBoxLayout()
    lay.setSpacing(spacing)
    lay.setContentsMargins(*margins)
    for it in items:
        if it is None:
            lay.addStretch(1)
        else:
            if isinstance(it, QWidget):
                lay.addWidget(it)
            else:
                lay.addLayout(it)
    return lay


def _hover_anim(owner, setter, duration: int = 160) -> QVariantAnimation:
    anim = QVariantAnimation(owner)
    anim.setDuration(duration)
    anim.setEasingCurve(QEasingCurve.OutCubic)
    anim.valueChanged.connect(setter)
    return anim


class HudPanel(QFrame):
    def __init__(
        self, accent: str, margins, spacing: int, cut: float = 12, parent=None
    ):
        super().__init__(parent)
        self.accent = accent
        self.cut = cut
        self.intensity = 1.0
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(*margins)
        self.body.setSpacing(spacing)

    def set_accent(self, accent: str) -> None:
        self.accent = accent
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        fx.paint_panel(p, QRectF(self.rect()), self.accent, self.cut, self.intensity)
        p.end()


_QWIDGETSIZE_MAX = 16777215


class _Chevron(QAbstractButton):
    """Tombol segitiga: menunjuk ke bawah = kartu tertutup (klik untuk membuka), ke atas = terbuka."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(26, 22)
        self.setCursor(Qt.PointingHandCursor)
        self.up = False
        self._hover = False

    def set_up(self, up: bool) -> None:
        self.up = up
        self.update()

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        cx, cy = (self.width() / 2.0, self.height() / 2.0)
        d = 3.0 if self.up else (-3.0)
        path = QPainterPath()
        path.moveTo(cx - 5, cy + d)
        path.lineTo(cx + 5, cy + d)
        path.lineTo(cx, cy - d)
        path.closeSubpath()
        p.fillPath(path, QColor(theme.GOLD_HI if self._hover else theme.GOLD))
        p.end()


class HudCard(HudPanel):
    """Panel + header: ikon, JUDUL, slot kanan (header_right), garis pemisah.\n\n    Isi kartu ada di `content` (widget pembungkus); `body` adalah layout isi itu. Setelah\n    `make_collapsible(...)` header mendapat tombol segitiga untuk menutup / membuka isi."""

    HEADER_H = 34

    def __init__(
        self,
        title: str,
        icon: str = '',
        accent: str = theme.RED,
        parent=None,
        spacing: int = 8,
    ):
        super().__init__(
            accent=accent, margins=(14, 10, 14, 14), spacing=spacing, parent=parent
        )
        head = QHBoxLayout()
        head.setSpacing(8)
        head.setContentsMargins(0, 0, 0, 6)
        self.icon_label = QLabel()
        if icon:
            self.icon_label.setPixmap(assets.icon_pixmap(icon, theme.GOLD, 16))
        self.icon_label.setFixedSize(18, 18)
        head.addWidget(self.icon_label)
        self.title_label = caps(title, 9.5, theme.TEXT, 1.8)
        head.addWidget(self.title_label)
        head.addStretch(1)
        self.header_right = QHBoxLayout()
        self.header_right.setSpacing(6)
        head.addLayout(self.header_right)
        outer = self.body
        outer.addLayout(head)
        self.content = QWidget()
        self._content_layout = QVBoxLayout(self.content)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(spacing)
        outer.addWidget(self.content)
        self.body = self._content_layout
        self.collapsed = False
        self.chevron = None
        self._card_key = ''
        self._on_collapse = None
        self._collapse_anim = None

    def set_title(self, text: str) -> None:
        self.title_label.setText(text.upper())

    def make_collapsible(
        self, key: str, collapsed: bool = True, on_change=None
    ) -> None:
        """Beri header tombol segitiga. `on_change(key, collapsed)` dipanggil saat PENGGUNA membuka / menutup."""
        self._card_key, self._on_collapse = (key, on_change)
        if self.chevron is None:
            self.chevron = _Chevron()
            self.chevron.clicked.connect(lambda: self.set_collapsed(not self.collapsed))
            self.header_right.addWidget(self.chevron)
        self.collapsed = not collapsed
        self.set_collapsed(collapsed, animate=False, notify=False)

    def set_collapsed(
        self, collapsed: bool, animate: bool = True, notify: bool = True
    ) -> None:
        if self.chevron is None or collapsed == self.collapsed:
            return None
        else:
            self.collapsed = collapsed
            self.chevron.set_up(not collapsed)
            self.chevron.setToolTip(
                tr('king.card_expand' if collapsed else 'king.card_collapse')
            )
            if self._collapse_anim is not None:
                self._collapse_anim.stop()
                self._collapse_anim = None
            if not animate or not self.isVisible():
                self.content.setMaximumHeight(_QWIDGETSIZE_MAX)
                self.content.setVisible(not collapsed)
            else:
                start = self.content.height() if collapsed else 0
                if not collapsed:
                    self.content.setMaximumHeight(0)
                    self.content.show()
                end = 0 if collapsed else self.content.sizeHint().height()
                anim = QVariantAnimation(self)
                anim.setDuration(170)
                anim.setEasingCurve(QEasingCurve.OutCubic)
                anim.setStartValue(float(start))
                anim.setEndValue(float(end))
                anim.valueChanged.connect(
                    lambda v: self.content.setMaximumHeight(max(0, int(v)))
                )
                anim.finished.connect(lambda: self._finish_collapse(collapsed))
                self._collapse_anim = anim
                anim.start()
            self.updateGeometry()
            self.update()
            if notify and self._on_collapse is not None:
                self._on_collapse(self._card_key, collapsed)

    def _finish_collapse(self, collapsed: bool) -> None:
        self.content.setMaximumHeight(_QWIDGETSIZE_MAX)
        if collapsed:
            self.content.hide()
        self._collapse_anim = None

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if self.collapsed:
            p.end()
            return
        else:
            y = self.HEADER_H + 4
            grad = QLinearGradient(14, y, self.width() - 14, y)
            grad.setColorAt(0, theme.qc(self.accent, 0.75))
            grad.setColorAt(0.45, theme.qc(theme.GOLD, 0.35))
            grad.setColorAt(1, theme.qc(self.accent, 0.0))
            p.setPen(QPen(grad, 1))
            p.drawLine(QPointF(14, y), QPointF(self.width() - 14, y))
            p.end()


_VARIANTS = {
    'primary': ('#1a2a1a', '#0d1a0d', '#3d8a40', theme.TEXT, theme.GREEN),
    'gold': ('#2a2010', '#1a1408', '#8a6a20', theme.TEXT, theme.GOLD),
    'ghost': ('#0f0f0f', '#080808', '#2a2a2a', theme.TEXT, theme.LINE),
    'danger': ('#2a1010', '#1a0808', '#8a3030', theme.TEXT, theme.RED),
    'success': ('#0f2a1a', '#081a0f', '#20a050', theme.TEXT, theme.GREEN),
}


class KButton(QAbstractButton):
    def __init__(
        self,
        text: str = '',
        icon: str = '',
        variant: str = 'ghost',
        parent=None,
        small: bool = False,
    ):
        super().__init__(parent)
        self.setText(text)
        self._icon = icon
        self.variant = variant
        self.small = small
        self._hover = 0.0
        self._anim = _hover_anim(self, self._set_hover)
        self.setCursor(Qt.PointingHandCursor)
        self.setFont(theme.font(8.5 if small else 9.5, spacing=1.0))
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

    def set_variant(self, variant: str) -> None:
        self.variant = variant
        self.update()

    def set_icon_name(self, name: str) -> None:
        self._icon = name
        self.updateGeometry()
        self.update()

    def _set_hover(self, v) -> None:
        self._hover = float(v)
        self.update()

    def enterEvent(self, e):
        self._anim.stop()
        self._anim.setStartValue(self._hover)
        self._anim.setEndValue(1.0)
        self._anim.start()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._anim.stop()
        self._anim.setStartValue(self._hover)
        self._anim.setEndValue(0.0)
        self._anim.start()
        super().leaveEvent(e)

    def sizeHint(self) -> QSize:
        fm = QFontMetricsF(self.font())
        w = fm.horizontalAdvance(self.text().upper()) + (26 if self.small else 34)
        if self._icon:
            w += 20 if self.text() else 0
        h = 28 if self.small else 34
        return QSize(int(max(w, h + 4)), h)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def paintEvent(self, _event):
        top, bot, border, text_c, glow = _VARIANTS.get(self.variant, _VARIANTS['ghost'])
        if not self.isEnabled():
            top, bot, border, text_c, glow = (
                '#120a0c',
                '#0a0607',
                '#2a1419',
                theme.TEXT_MUTE,
                theme.LINE,
            )
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1.5, 1.5, (-1.5), (-1.5))
        cut = 6 if self.small else 8
        path = fx.chamfer_path(r, cut, fx.TL | fx.BR)
        grad = QLinearGradient(r.topLeft(), r.bottomLeft())
        down = self.isDown()
        grad.setColorAt(
            0, fx.lerp_color(top, glow, 0.18 * self._hover) if not down else QColor(bot)
        )
        grad.setColorAt(1, QColor(bot))
        p.fillPath(path, grad)
        if self.isEnabled():
            fx.glow_stroke(
                p,
                path,
                theme.qc(border, 0.55 + 0.45 * self._hover),
                1.2,
                6 + 6 * self._hover,
                4,
            )
            0.6 + 0.8 * self._hover
        else:
            p.strokePath(path, QPen(QColor(border), 1))
        fm = QFontMetricsF(self.font())
        label = self.text().upper()
        tw = fm.horizontalAdvance(label)
        icon_w = 16 if self._icon else 0
        gap = 7 if self._icon and label else 0
        x = (r.width() - (tw + icon_w + gap)) / 2 + r.left()
        if self._icon:
            pm = assets.icon_pixmap(self._icon, text_c, 16 if not self.small else 14)
            p.drawPixmap(
                QPointF(x, r.center().y() - pm.height() / pm.devicePixelRatio() / 2), pm
            )
            x += icon_w + gap
        p.setFont(self.font())
        p.setPen(QColor(text_c))
        p.drawText(
            QRectF(x, r.top(), tw + 2, r.height()),
            Qt.AlignVCenter | Qt.AlignLeft,
            label,
        )
        p.end()


class IconButton(QAbstractButton):
    pass

    def __init__(
        self,
        icon: str,
        size: int = 30,
        icon_size: int = 15,
        variant: str = 'plain',
        tooltip: str = '',
        parent=None,
    ):
        super().__init__(parent)
        self._icon = icon
        self._icon_size = icon_size
        self.variant = variant
        self._hover = 0.0
        self._anim = _hover_anim(self, self._set_hover, 120)
        self.setFixedSize(size, size)
        self.setCursor(Qt.PointingHandCursor)
        if tooltip:
            self.setToolTip(tooltip)

    def set_icon_name(self, name: str) -> None:
        self._icon = name
        self.update()

    def _set_hover(self, v) -> None:
        self._hover = float(v)
        self.update()

    def enterEvent(self, e):
        self._anim.stop()
        self._anim.setStartValue(self._hover)
        self._anim.setEndValue(1.0)
        self._anim.start()

    def leaveEvent(self, e):
        self._anim.stop()
        self._anim.setStartValue(self._hover)
        self._anim.setEndValue(0.0)
        self._anim.start()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(2, 2, (-2), (-2))
        hot = theme.RED if self.variant == 'close' else theme.GOLD
        if self._hover > 0.01:
            path = fx.chamfer_path(r, 5, fx.TL | fx.BR)
            fill = theme.qc(
                theme.RED if self.variant == 'close' else '#2a1015', 0.85 * self._hover
            )
            p.fillPath(path, fill)
            p.strokePath(path, QPen(theme.qc(hot, 0.7 * self._hover), 1))
        color = fx.lerp_color(
            theme.TEXT_DIM,
            '#ffffff' if self.variant == 'close' else theme.GOLD_HI,
            self._hover,
        )
        if not self.isEnabled():
            color = QColor(theme.TEXT_MUTE)
        pm = assets.icon_pixmap(self._icon, color.name(), self._icon_size)
        size = pm.width() / pm.devicePixelRatio()
        p.drawPixmap(QPointF(r.center().x() - size / 2, r.center().y() - size / 2), pm)
        p.end()


class CommandButton(QAbstractButton):
    """Tombol perintah utama: START / STOP AUTOTRADE. Ringkas (156 x 48) -\n    hidup di sudut kiri-bawah kartu Crown Reactor."""

    SIZE = QSize(158, 48)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.mode = 'start'
        self.title = 'START'
        self.subtitle = ''
        self._t = 0.0
        self._hover = 0.0
        self._anim = _hover_anim(self, self._set_hover, 200)
        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(self.SIZE)

    def set_state(self, mode: str, title: str, subtitle: str = '') -> None:
        self.mode, self.title, self.subtitle = (mode, title, subtitle)
        self.setCursor(Qt.WaitCursor if mode == 'busy' else Qt.PointingHandCursor)
        self.update()

    def _tick(self) -> None:
        self._t += 0.05
        if self.isVisible():
            self.update()

    def _set_hover(self, v) -> None:
        self._hover = float(v)

    def enterEvent(self, e):
        self._anim.stop()
        self._anim.setStartValue(self._hover)
        self._anim.setEndValue(1.0)
        self._anim.start()

    def leaveEvent(self, e):
        self._anim.stop()
        self._anim.setStartValue(self._hover)
        self._anim.setEndValue(0.0)
        self._anim.start()

    def paintEvent(self, _event):
        stop, busy = (self.mode == 'stop', self.mode == 'busy')
        base = theme.RED if stop else theme.GOLD if busy else theme.GREEN
        deep = '#4a0610' if stop else '#3a2a08' if busy else '#06331b'
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(3, 3, (-3), (-3))
        path = fx.chamfer_path(r, 11, fx.TL | fx.BR)
        pulse = 0.5 + 0.5 * math.sin(self._t * (3.6 if stop else 2.0))
        g = QLinearGradient(r.topLeft(), r.bottomRight())
        g.setColorAt(
            0, fx.lerp_color(deep, base, 0.22 + 0.1 * self._hover + 0.08 * pulse)
        )
        g.setColorAt(0.6, QColor(deep))
        g.setColorAt(1, QColor('#050204'))
        p.fillPath(path, g)
        sweep = self._t % 3.0 / 3.0
        sx = r.left() - 60 + (r.width() + 120) * sweep
        shine = QLinearGradient(sx - 30, r.top(), sx + 30, r.bottom())
        shine.setColorAt(0, theme.qc('#ffffff', 0.0))
        shine.setColorAt(0.5, theme.qc('#ffffff', 0.16))
        shine.setColorAt(1, theme.qc('#ffffff', 0.0))
        p.save()
        p.setClipPath(path)
        p.fillRect(r, shine)
        p.restore()
        fx.glow_stroke(
            p, path, theme.qc(base, 0.9), 1.5, 10 + 7 * pulse + 5 * self._hover
        )
        cy = r.center().y()
        ex = r.left() + 22
        halo = QRadialGradient(ex, cy, 20)
        halo.setColorAt(0, theme.qc(base, 0.5 + 0.25 * pulse))
        halo.setColorAt(1, theme.qc(base, 0.0))
        p.setPen(Qt.NoPen)
        p.setBrush(halo)
        p.drawEllipse(QPointF(ex, cy), 20, 20)
        p.setBrush(theme.qc('#050204', 0.9))
        p.setPen(QPen(theme.qc(base, 0.95), 1.4))
        p.drawEllipse(QPointF(ex, cy), 13, 13)
        if busy:
            p.setPen(QPen(QColor(base), 2.2, Qt.SolidLine, Qt.RoundCap))
            p.drawArc(
                QRectF(ex - 8, cy - 8, 16, 16), int(-self._t * 360 * 16) % 5760, 4160
            )
        else:
            pm = assets.icon_pixmap('stop' if stop else 'play', base, 13)
            p.drawPixmap(QPointF(ex - 6.5 + (0 if stop else 1), cy - 6.5), pm)
        tx = ex + 22
        width = r.right() - tx - 6
        f = theme.font(12.5, spacing=1.6)
        p.setFont(f)
        p.setPen(QColor('#ffffff' if not busy else theme.GOLD_HI))
        p.drawText(
            QRectF(tx, cy - 17, width, 20),
            Qt.AlignLeft | Qt.AlignVCenter,
            QFontMetricsF(f).elidedText(self.title, Qt.ElideRight, width),
        )
        if self.subtitle:
            f2 = theme.font(7, spacing=1.2)
            p.setFont(f2)
            p.setPen(theme.qc(base, 0.95))
            p.drawText(
                QRectF(tx, cy + 2, width, 14),
                Qt.AlignLeft | Qt.AlignVCenter,
                QFontMetricsF(f2).elidedText(
                    self.subtitle.upper(), Qt.ElideRight, width
                ),
            )
        p.end()


class KSwitch(QAbstractButton):
    def __init__(self, checked: bool = False, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self._pos = 1.0 if checked else 0.0
        self._anim = _hover_anim(self, self._set_pos, 180)
        self.toggled.connect(self._animate)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(44, 22)

    def _set_pos(self, v) -> None:
        self._pos = float(v)
        self.update()

    def _animate(self, on: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def setChecked(self, on: bool) -> None:
        super().setChecked(on)
        if not self._anim_running():
            self._pos = 1.0 if on else 0.0
            self.update()

    def _anim_running(self) -> bool:
        return (
            getattr(self, '_anim', None) is not None
            and self._anim.state() == QVariantAnimation.Running
        )

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 3, (-1), (-3))
        path = fx.chamfer_path(r, 5, fx.TL | fx.BR)
        on_c = theme.GREEN if self.isEnabled() else theme.TEXT_MUTE
        track = fx.lerp_color('#1a0b10', '#0b3d22', self._pos)
        p.fillPath(path, track)
        p.strokePath(path, QPen(fx.lerp_color(theme.LINE_HI, on_c, self._pos), 1.2))
        kx = r.left() + 3 + (r.width() - 22) * self._pos
        knob = fx.chamfer_path(
            QRectF(kx, r.top() + 2.5, 16, r.height() - 5), 3, fx.TL | fx.BR
        )
        p.fillPath(knob, fx.lerp_color(theme.TEXT_DIM, on_c, self._pos))
        p.end()


class _SegButton(QAbstractButton):
    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.setText(text)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFont(theme.font(8.5, spacing=1.0))
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(28)

    def sizeHint(self) -> QSize:
        return QSize(
            int(QFontMetricsF(self.font()).horizontalAdvance(self.text().upper()) + 22),
            28,
        )

    def minimumSizeHint(self) -> QSize:
        return QSize(
            int(
                QFontMetricsF(self.font()).horizontalAdvance(self.text().upper()) * 0.62
                + 8
            ),
            28,
        )

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, (-1), (-1))
        path = fx.chamfer_path(r, 5, fx.TL | fx.BR)
        if self.isChecked():
            g = QLinearGradient(r.topLeft(), r.bottomLeft())
            g.setColorAt(0, QColor('#b30f29'))
            g.setColorAt(1, QColor('#4d0610'))
            p.fillPath(path, g)
            fx.glow_stroke(p, path, theme.qc(theme.RED_HOT, 0.9), 1.1, 6, 3, 0.8)
            color = '#ffffff'
        else:
            p.fillPath(path, QColor('#0d0609'))
            p.strokePath(
                path, QPen(QColor(theme.LINE if self.isEnabled() else '#1e0d11'), 1)
            )
            color = theme.TEXT_DIM if self.isEnabled() else theme.TEXT_MUTE
            if self.underMouse() and self.isEnabled():
                color = theme.GOLD_HI
        f = self.font()
        label = self.text().upper()
        avail = r.width() - 8
        width = QFontMetricsF(f).horizontalAdvance(label)
        if width > avail and width > 0:
            f = QFont(f)
            f.setPointSizeF(max(6.2, f.pointSizeF() * avail / width))
            f.setLetterSpacing(QFont.AbsoluteSpacing, 0.2)
        p.setFont(f)
        p.setPen(QColor(color))
        p.drawText(
            r,
            Qt.AlignCenter,
            QFontMetricsF(f).elidedText(label, Qt.ElideRight, avail + 4),
        )
        p.end()


class Segmented(QWidget):
    changed = Signal(str)

    def __init__(
        self,
        items: list[tuple[str, str]],
        current: str = '',
        parent=None,
        spacing: int = 4,
    ):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(spacing)
        self.buttons = {}
        for key, text in items:
            b = _SegButton(text)
            b.clicked.connect(lambda _c=False, k=key: self.set_value(k, emit=True))
            lay.addWidget(b)
            self.buttons[key] = b
        self._value = ''
        self.set_value(current or (items[0][0] if items else ''))

    def value(self) -> str:
        return self._value

    def set_value(self, key: str, emit: bool = False) -> None:
        if key not in self.buttons:
            return
        else:
            changed = key != self._value
            self._value = key
            for k, b in self.buttons.items():
                b.setChecked(k == key)
            if emit and changed:
                self.changed.emit(key)

    def set_text(self, key: str, text: str) -> None:
        if key in self.buttons:
            self.buttons[key].setText(text)
            self.buttons[key].updateGeometry()


class Chip(QWidget):
    """Label status kecil: titik bercahaya + TEKS, bertakik."""

    def __init__(
        self, text: str = '', color: str = theme.TEXT_DIM, dot: bool = True, parent=None
    ):
        super().__init__(parent)
        self.text, self.color, self.dot = (text, color, dot)
        self.pulse = False
        self._t = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(60)
        self._timer.timeout.connect(self._tick)
        self.setFont(theme.font(8, spacing=1.0))
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

    def set_state(self, text: str, color: str, pulse: bool = False) -> None:
        self.text, self.color, self.pulse = (text, color, pulse)
        if pulse:
            self._timer.start()
        else:
            self._timer.stop()
        self.updateGeometry()
        self.update()

    def _tick(self) -> None:
        self._t += 0.06
        self.update()

    def sizeHint(self) -> QSize:
        w = QFontMetricsF(self.font()).horizontalAdvance(self.text.upper()) + (
            26 if self.dot else 16
        )
        return QSize(int(w), 22)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, (-0.5), (-0.5))
        path = fx.chamfer_path(r, 5, fx.TL | fx.BR)
        p.fillPath(path, theme.qc(self.color, 0.1))
        p.strokePath(path, QPen(theme.qc(self.color, 0.55), 1))
        x = r.left() + 8
        if self.dot:
            a = 0.55 + 0.45 * math.sin(self._t * 4) if self.pulse else 1.0
            halo = QRadialGradient(x + 2.5, r.center().y(), 6)
            halo.setColorAt(0, theme.qc(self.color, 0.7 * a))
            halo.setColorAt(1, theme.qc(self.color, 0.0))
            p.setPen(Qt.NoPen)
            p.setBrush(halo)
            p.drawEllipse(QPointF(x + 2.5, r.center().y()), 6, 6)
            p.setBrush(theme.qc(self.color, a))
            p.drawEllipse(QPointF(x + 2.5, r.center().y()), 2.6, 2.6)
            x += 10
        p.setFont(self.font())
        p.setPen(QColor(self.color))
        p.drawText(
            QRectF(x, r.top(), r.right() - x - 4, r.height()),
            Qt.AlignVCenter | Qt.AlignLeft,
            self.text.upper(),
        )
        p.end()


class StatTile(QWidget):
    """LABEL kecil + angka besar beranimasi + keterangan."""

    def __init__(
        self, label: str, accent: str = theme.GOLD, big: bool = False, parent=None
    ):
        super().__init__(parent)
        self.label, self.accent, self.big = (label, accent, big)
        self.value_text = '—'
        self.sub = ''
        self.value_color = theme.TEXT
        self._value = None
        self._shown = 0.0
        self._fmt = '{:,.2f}'
        self._flash = 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(520)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._on_anim)
        self._flash_anim = QVariantAnimation(self)
        self._flash_anim.setDuration(900)
        self._flash_anim.setStartValue(1.0)
        self._flash_anim.setEndValue(0.0)
        self._flash_anim.valueChanged.connect(
            lambda v: (setattr(self, '_flash', float(v)), self.update())
        )
        self.setMinimumHeight(64 if big else 54)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def sizeHint(self) -> QSize:
        return QSize(150, 64 if self.big else 54)

    def set_text(self, text: str, color: str = theme.TEXT, sub: str = '') -> None:
        self._value = None
        self.value_text, self.value_color, self.sub = (text, color, sub)
        self.update()

    def set_value(
        self,
        value: float,
        fmt: str = '{:,.2f}',
        color: str = theme.TEXT,
        sub: str = '',
        prefix: str = '',
    ) -> None:
        self._fmt, self.value_color, self.sub, self._prefix = (fmt, color, sub, prefix)
        if self._value is not None and abs(value - self._value) > 1e-09:
            self._flash_anim.stop()
            self._flash_anim.start()
        start = self._shown if self._value is not None else value
        self._value = value
        self._anim.stop()
        self._anim.setStartValue(float(start))
        self._anim.setEndValue(float(value))
        self._anim.start()
        self._on_anim(start)

    def _on_anim(self, v) -> None:
        self._shown = float(v)
        self.value_text = getattr(self, '_prefix', '') + self._fmt.format(self._shown)
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, (-0.5), (-0.5))
        path = fx.chamfer_path(r, 8, fx.TL | fx.BR)
        g = QLinearGradient(r.topLeft(), r.bottomLeft())
        g.setColorAt(0, QColor('#120709'))
        g.setColorAt(1, QColor('#080406'))
        p.fillPath(path, g)
        if self._flash > 0:
            p.fillPath(path, theme.qc(self.value_color, 0.1 * self._flash))
        p.strokePath(path, QPen(theme.qc(theme.LINE_HI, 0.9), 1))
        p.fillRect(
            QRectF(r.left() + 1, r.top() + 10, 2.4, r.height() - 20),
            theme.qc(self.accent, 0.9),
        )
        p.setFont(theme.font(7.5, spacing=1.4))
        p.setPen(QColor(theme.TEXT_DIM))
        label_rect = QRectF(r.left() + 12, r.top() + 6, r.width() - 18, 16)
        p.drawText(
            label_rect,
            Qt.AlignLeft | Qt.AlignVCenter,
            QFontMetricsF(p.font()).elidedText(
                self.label.upper(), Qt.ElideRight, label_rect.width()
            ),
        )
        size = 16.5 if self.big else 13.5
        p.setFont(theme.font(size, spacing=0.4))
        p.setPen(QColor(self.value_color))
        val_rect = QRectF(r.left() + 12, r.top() + 20, r.width() - 18, size * 1.9)
        p.drawText(
            val_rect,
            Qt.AlignLeft | Qt.AlignVCenter,
            QFontMetricsF(p.font()).elidedText(
                self.value_text, Qt.ElideRight, val_rect.width()
            ),
        )
        if self.sub:
            p.setFont(theme.font(7.5, display=False))
            p.setPen(QColor(theme.TEXT_MUTE))
            sub_rect = QRectF(r.left() + 12, r.bottom() - 17, r.width() - 18, 14)
            p.drawText(
                sub_rect,
                Qt.AlignLeft | Qt.AlignVCenter,
                QFontMetricsF(p.font()).elidedText(
                    self.sub, Qt.ElideRight, sub_rect.width()
                ),
            )
        p.end()


class RingGauge(QWidget):
    def __init__(self, caption: str = '', color: str = theme.GREEN, parent=None):
        super().__init__(parent)
        self.caption, self.color = (caption, color)
        self.center_text = '—'
        self._v = 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(700)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(
            lambda v: (setattr(self, '_v', float(v)), self.update())
        )
        self.setFixedSize(84, 84)

    def set_value(
        self, fraction: float | None, text: str, color: str | None = None
    ) -> None:
        self.center_text = text
        if color:
            self.color = color
        target = max(0.0, min(1.0, fraction or 0.0))
        self._anim.stop()
        self._anim.setStartValue(self._v)
        self._anim.setEndValue(target)
        self._anim.start()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(7, 7, (-7), (-7))
        p.setPen(QPen(QColor('#1e0c11'), 7, Qt.SolidLine, Qt.FlatCap))
        p.drawArc(r, 0, 5760)
        for i in range(24):
            a = math.radians(i * 15)
            c = r.center()
            rr = r.width() / 2 + 6
            p.setPen(QPen(theme.qc(theme.GOLD, 0.35), 1))
            p.drawLine(
                QPointF(c.x() + (rr - 2) * math.cos(a), c.y() + (rr - 2) * math.sin(a)),
                QPointF(c.x() + rr * math.cos(a), c.y() + rr * math.sin(a)),
            )
        if self._v > 0:
            span = int(-self._v * 360 * 16)
            p.setPen(QPen(theme.qc(self.color, 0.25), 13, Qt.SolidLine, Qt.FlatCap))
            p.drawArc(r, 1440, span)
            p.setPen(QPen(QColor(self.color), 7, Qt.SolidLine, Qt.FlatCap))
            p.drawArc(r, 1440, span)
        p.setFont(theme.font(13))
        p.setPen(QColor(theme.TEXT))
        p.drawText(r.adjusted(0, (-6), 0, (-6)), Qt.AlignCenter, self.center_text)
        p.setFont(theme.font(6.5, spacing=1.2))
        p.setPen(QColor(theme.TEXT_DIM))
        p.drawText(r.adjusted(0, 18, 0, 18), Qt.AlignCenter, self.caption.upper())
        p.end()


class Divider(QWidget):
    def __init__(self, color: str = theme.RED, parent=None):
        super().__init__(parent)
        self.color = color
        self.setFixedHeight(9)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        y = self.height() / 2
        g = QLinearGradient(0, y, self.width(), y)
        g.setColorAt(0, theme.qc(self.color, 0.0))
        g.setColorAt(0.5, theme.qc(self.color, 0.65))
        g.setColorAt(1, theme.qc(self.color, 0.0))
        p.setPen(QPen(g, 1))
        p.drawLine(QPointF(0, y), QPointF(self.width(), y))
        c = self.width() / 2
        diamond = QPainterPath()
        diamond.moveTo(c, y - 3.5)
        diamond.lineTo(c + 3.5, y)
        diamond.lineTo(c, y + 3.5)
        diamond.lineTo(c - 3.5, y)
        diamond.closeSubpath()
        p.fillPath(diamond, QColor(theme.GOLD))
        p.end()


class NumberEdit(QDoubleSpinBox):
    pass

    def __init__(
        self,
        value: float = 0.0,
        decimals: int = 2,
        minimum: float = 0.0,
        maximum: float = 1000000000.0,
        step: float = 1.0,
        suffix: str = '',
        parent=None,
    ):
        super().__init__(parent)
        self.setDecimals(decimals)
        self.setRange(minimum, maximum)
        self.setSingleStep(step)
        self.setButtonSymbols(QDoubleSpinBox.NoButtons)
        self.setValue(value)
        self.setKeyboardTracking(False)
        if suffix:
            self.setSuffix(suffix)
        self.setFocusPolicy(Qt.StrongFocus)

    def wheelEvent(self, event):
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


class KCombo(QComboBox):
    """Combo yang tidak berubah oleh roda mouse saat halaman digulir, dan\n    lebarnya TIDAK mengikuti item terpanjang (jendela ramping 450 px)."""

    def __init__(self, parent=None, min_chars: int = 6):
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.setMinimumContentsLength(min_chars)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def wheelEvent(self, event):
        if self.hasFocus() and self.view().isVisible():
            super().wheelEvent(event)
        else:
            event.ignore()


class ModelPicker(KCombo):
    """Model AI: ketik untuk menyaring ratusan model (cocok di tengah kata)."""

    changed = Signal(str)

    def __init__(self, placeholder: str = '', parent=None):
        super().__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.NoInsert)
        self.lineEdit().setPlaceholderText(placeholder)
        completer = QCompleter(self.model(), self)
        completer.setFilterMode(Qt.MatchContains)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setCompletionMode(QCompleter.PopupCompletion)

        self.setStyleSheet(
            f'QComboBox {{ background-color: #0d0609; border: 1px solid {theme.RED_DEEP}; selection-background-color: #3a0c16; }}'
        )
        self.setCompleter(completer)
        self.lineEdit().editingFinished.connect(lambda: self.changed.emit(self.value()))
        self.activated.connect(lambda _i: self.changed.emit(self.value()))

    def set_models(self, models: list[str]) -> None:
        current = self.value()
        self.blockSignals(True)
        self.clear()
        self.addItems(sorted(set(models), key=str.lower))
        self.setEditText(current)
        self.blockSignals(False)

    def value(self) -> str:
        return self.currentText().strip()

    def set_value(self, text: str) -> None:
        self.blockSignals(True)
        idx = self.findText(text)
        if idx >= 0:
            self.setCurrentIndex(idx)
        self.setEditText(text or '')
        self.blockSignals(False)
