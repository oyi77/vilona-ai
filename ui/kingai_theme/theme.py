"""
theme.py
========
Bahasa visual Vilona AI: "Royal War-Room" - hitam obsidian, merah darah
bercahaya, aksen emas mahkota. Satu sumber kebenaran warna, font, dan QSS
global untuk widget standar Qt.
"""

from config import DATA_DIR, ASSETS_DIR, BRAND_DIR, ICONS_DIR, UI_DIR
from core.qt import QColor, QFont

APP_NAME = 'Vilona AI'
BG = '#050204'
BG_2 = '#0a0407'
PANEL_TOP = '#160910'
PANEL_BOT = '#090406'
SUNKEN = '#070305'
LINE = '#3b1119'
LINE_HI = '#5c1a26'
RED = '#ff2d4a'
RED_HOT = '#ff5a70'
RED_DEEP = '#8e0018'
GOLD = '#f2c062'
GOLD_HI = '#ffe2a0'
GOLD_DIM = '#9a7330'
GREEN = '#2bff88'
GREEN_DEEP = '#0b7a3c'
AMBER = '#ffb547'
CYAN = '#5fd8ff'
TEXT = '#f6ece6'
TEXT_DIM = '#a8949a'
TEXT_MUTE = '#6d5a60'
FONT_DISPLAY = 'Bahnschrift SemiBold SemiConden'
FONT_DISPLAY_LIGHT = 'Bahnschrift SemiLight SemiConde'
FONT_BODY = 'Segoe UI'
FONT_MONO = 'Cascadia Mono'


def qc(hex_color=None, alpha=None):
    color = QColor(hex_color)
    if alpha is not None:
        color.setAlphaF(max(0.0, min(1.0, alpha)))
    return color


def font(size=9, display=False, weight=None, spacing=0.0, mono=False):
    family = FONT_MONO if mono else FONT_BODY
    f = QFont(family)
    f.setPointSizeF(size)
    if weight is not None:
        f.setWeight(weight)
    if spacing:
        f.setLetterSpacing(QFont.AbsoluteSpacing, spacing)
    f.setHintingPreference(QFont.PreferNoHinting)
    return f


def _icon_url(name=None):
    return (ICONS_DIR / f'{name}.png').as_posix()


def app_stylesheet():
    check = _icon_url('check')
    chevron = _icon_url('chevron_down')
    return f"""
* {{ font-family: '{FONT_BODY}'; font-size: 9pt; color: {TEXT}; outline: none; }}
QWidget#ContentArea, QStackedWidget#PageStack {{ background: transparent; }}
QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}
QLabel {{ background: transparent; }}
QToolTip {{ background-color: #140a0d; color: {TEXT}; border: 1px solid {RED_DEEP}; padding: 6px 8px; border-radius: 4px; }}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QDateEdit {{
    background-color: {SUNKEN}; border: 1px solid {LINE}; border-radius: 4px;
    padding: 5px 9px; min-height: 18px; selection-background-color: {RED_DEEP}; color: {TEXT};
}}
QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover, QComboBox:hover, QDateEdit:hover {{ border-color: {LINE_HI}; }}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QDateEdit:focus {{ border-color: {RED}; background-color: #0c0507; }}
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {{ color: {TEXT_MUTE}; border-color: #241016; background-color: #080406; }}
QCheckBox {{ spacing: 8px; background: transparent; }}
QCheckBox::indicator {{ width: 15px; height: 15px; border: 1px solid {LINE}; background: {SUNKEN}; }}
QCheckBox::indicator:checked {{ image: url('{check}'); background: {RED_DEEP}; }}
QComboBox::down-arrow {{ image: url('{chevron}'); width: 11px; height: 11px; }}
"""
