"""Stub for KingAI assets — icons/brand not available, returns blank."""
from PySide6.QtCore import QSize
from PySide6.QtGui import QPixmap, QColor

def pixmap(path):
    pm = QPixmap(20, 20)
    pm.fill(QColor('#000000'))
    return pm

def brand(name):
    return pixmap('')

def ui(name):
    return pixmap('')

def icon_pixmap(name, color, size=20, dpr=1.0):
    pm = QPixmap(size, size)
    pm.fill(QColor(color))
    return pm
