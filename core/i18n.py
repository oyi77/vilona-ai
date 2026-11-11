# Decompiled with PyLingual (https://pylingual.io)
# Internal filename: 'kingai\\core\\i18n.py'
# Bytecode version: 3.10.b1 (3439)
# Source timestamp: 1970-01-01 00:00:00 UTC (0)

"""\ni18n.py\n=======\nTerjemahan terpusat KingAI (Indonesia / English).\n\n    from core.i18n import tr\n    tr(\"king.cmd_start\")                      # teks statis\n    tr(\"autotrade.log_started\", symbol=s, mode=m)\n\nDua sumber teks digabung di sini:\n    i18n_strings.py  teks mesin Auto Trade yang diwarisi QueenAI (log, eksekusi,\n                     News Guard, router model) - dipangkas ke kunci yang dipakai\n    i18n_king.py     teks antarmuka KingAI (kunci \"king.*\")\nKunci yang tidak ada di bahasa aktif jatuh ke Indonesia, lalu ke kunci itu\nsendiri - UI tidak pernah crash hanya karena terjemahan kurang.\n"""
global _current_language
from core.i18n_armada import STRINGS_ARMADA
from core.i18n_king import STRINGS_KING
from core.i18n_strings import STRINGS_ENGINE
from core.qt import QObject, Signal
LANGUAGES = {'id': 'Indonesia', 'en': 'English'}
_current_language = 'id'
class _I18nSignals(QObject):
    language_changed = Signal(str)
i18n_signals = _I18nSignals()
STRINGS: dict[str, dict[str, str]] = {}
for _source in [STRINGS_ENGINE, STRINGS_KING, STRINGS_ARMADA]:
    for _lang, _table in _source.items():
        STRINGS.setdefault(_lang, {}).update(_table)
def get_language() -> str:
    return _current_language
def set_language(lang: str) -> None:
    global _current_language
    if lang not in LANGUAGES or lang == _current_language:
        return None
    else:
        _current_language = lang
        i18n_signals.language_changed.emit(lang)
def tr(key: str, **kwargs) -> str:
    template = STRINGS.get(_current_language, {}).get(key)
    if template is None:
        template = STRINGS['id'].get(key, key)
    if kwargs:
        try:
            return template.format(**kwargs)
        except (KeyError, IndexError):
            return template
    else:
        return template