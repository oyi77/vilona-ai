from __future__ import annotations

from core.qt import (
    QBrush,
    QColor,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPointF,
    QRectF,
    Qt,
)
from ui.kingai_theme import theme
from ui import assets

(TL, TR, BR, BL) = (1, 2, 4, 8)
ALL_CORNERS = TL | TR | BR | BL

_hex_brush = None


def chamfer_path(rect, cut=0, corners=ALL_CORNERS):
    """Return a path with selected corners chamfered."""
    if rect is None:
        return QPainterPath()
    x0, y0, x1, y1 = rect.left(), rect.top(), rect.right(), rect.bottom()
    cut = min(float(cut), rect.width() / 2.0, rect.height() / 2.0)
    path = QPainterPath()
    path.moveTo(x0 + cut if corners & TL else x0, y0)
    if corners & TR:
        path.lineTo(x1 - cut, y0)
        path.lineTo(x1, y0 + cut)
    else:
        path.lineTo(x1, y0)
    if corners & BR:
        path.lineTo(x1, y1 - cut)
        path.lineTo(x1 - cut, y1)
    else:
        path.lineTo(x1, y1)
    if corners & BL:
        path.lineTo(x0 + cut, y1)
        path.lineTo(x0, y1 - cut)
    else:
        path.lineTo(x0, y1)
    if corners & TL:
        path.lineTo(x0, y0 + cut)
    path.closeSubpath()
    return path


def glow_stroke(p, path, color, width=1.0, glow=8, steps=5, strength=1.0):
    color = QColor(color)
    base_alpha = color.alphaF()
    for i in range(steps, 0, -1):
        stroke = QColor(color)
        alpha = base_alpha * strength * (0.04 + 0.12 * (steps - i) / steps)
        stroke.setAlphaF(alpha)
        p.strokePath(
            path,
            QPen(
                stroke,
                width + glow * i / steps,
                Qt.SolidLine,
                Qt.RoundCap,
                Qt.RoundJoin,
            ),
        )
    p.strokePath(path, QPen(color, width, Qt.SolidLine, Qt.FlatCap, Qt.MiterJoin))


def hex_brush():
    global _hex_brush
    if _hex_brush is None:
        try:
            _hex_brush = QBrush(assets.ui('hex_tile'))
        except Exception:
            _hex_brush = QBrush(QColor(theme.PANEL_TOP))
    return _hex_brush


def corner_brackets(p, rect, color, length=12, width=1.4, corners=TR | BL, inset=3):
    pen = QPen(QColor(color), width, Qt.SolidLine, Qt.SquareCap, Qt.MiterJoin)
    p.setPen(pen)
    r = rect.adjusted(inset, inset, -inset, -inset)
    if corners & TL:
        p.drawPolyline(
            [
                QPointF(r.left(), r.top() + length),
                r.topLeft(),
                QPointF(r.left() + length, r.top()),
            ]
        )
    if corners & TR:
        p.drawPolyline(
            [
                QPointF(r.right() - length, r.top()),
                r.topRight(),
                QPointF(r.right(), r.top() + length),
            ]
        )
    if corners & BR:
        p.drawPolyline(
            [
                QPointF(r.right(), r.bottom() - length),
                r.bottomRight(),
                QPointF(r.right() - length, r.bottom()),
            ]
        )
    if corners & BL:
        p.drawPolyline(
            [
                QPointF(r.left() + length, r.bottom()),
                r.bottomLeft(),
                QPointF(r.left(), r.bottom() - length),
            ]
        )


def paint_panel(
    p, rect, accent, cut=10, intensity=1.0, texture=False, brackets=True, top_light=True
):
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    r = QRectF(rect).adjusted(1.5, 1.5, -1.5, -1.5)
    path = chamfer_path(r, cut, TL | BR)
    grad = QLinearGradient(r.topLeft(), r.bottomLeft())
    grad.setColorAt(0, QColor(theme.PANEL_TOP))
    grad.setColorAt(1, QColor(theme.PANEL_BOT))
    p.fillPath(path, grad)
    if texture:
        p.save()
        p.setClipPath(path)
        p.setOpacity(0.55)
        p.fillPath(path, hex_brush())
        p.restore()
    if top_light:
        sheen = QLinearGradient(r.topLeft(), QPointF(r.left(), r.top() + 46))
        sheen.setColorAt(0, QColor(theme.qc(accent, 0.1 * intensity)))
        sheen.setColorAt(1, QColor(theme.qc(accent, 0)))
        p.fillPath(path, sheen)
    p.strokePath(path, QPen(QColor(theme.qc(theme.LINE_HI, 0.95)), 1))
    if brackets:
        corner_brackets(p, r, theme.qc(theme.GOLD, 0.85), 10, 1.4, TR | BL, 3)
    p.restore()
    return path


def paint_frame(p, rect, accent, cut=16):
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    r = QRectF(rect).adjusted(1.5, 1.5, -1.5, -1.5)
    path = chamfer_path(r, min(cut, r.width() / 2.0, r.height() / 2.0), TL | BR)
    p.strokePath(path, QPen(QColor(theme.qc(theme.LINE_HI, 0.95)), 1))
    corner_brackets(p, r, theme.qc(theme.GOLD, 0.85), 10, 1.4, TR | BL, 3)
    p.restore()


def lerp_color(a, b, t):
    a = QColor(a)
    b = QColor(b)
    t = max(0.0, min(1.0, float(t)))
    return QColor.fromRgbF(
        a.redF() + (b.redF() - a.redF()) * t,
        a.greenF() + (b.greenF() - a.greenF()) * t,
        a.blueF() + (b.blueF() - a.blueF()) * t,
        a.alphaF() + (b.alphaF() - a.alphaF()) * t,
    )
