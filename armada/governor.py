# Decompiled with PyLingual (https://pylingual.io)
# Internal filename: 'kingai\\armada\\governor.py'
# Bytecode version: 3.10.b1 (3439)
# Source timestamp: 1970-01-01 00:00:00 UTC (0)

# ***<module>: Failure: Compilation Error
"""\ngovernor.py\n===========\nRisk Governor lintas lane - penjaga SEBELUM entry baru dikirim.\n\nDua lapis (karena tiap akun MT5 hidup di proses worker sendiri):\n\n1. Lapis akun (worker, tiap entry) - `check_entry`:\n     - batas posisi+pending gabungan (akun ini + akun lain; angka akun lain\n       dikirim Hub lewat `External`),\n     - pair berkorelasi yang sedang terbuka di akun ini,\n     - halt global (rugi harian gabungan melewati batas).\n2. Lapis armada (Hub, tiap pembaruan statistik) - `external_for`: menghitung\n   `External` tiap akun dari ringkasan semua akun lalu mengirimkannya.\n\nMurni Python (tanpa Qt/MT5).\n"""
from __future__ import annotations
from dataclasses import dataclass
from armada.model import GovernorConfig
CORRELATED_GROUPS: tuple[frozenset[str], ...] = (
    frozenset({'EURUSD', 'GBPUSD'}),
    frozenset({'XAUUSD', 'XAGUSD'}),
    frozenset({'AUDUSD', 'NZDUSD'}),
)
def base_symbol(symbol: str) -> str:
    """\"EURUSDm\" / \"EURUSD.pro\" -> \"EURUSD\" (6 huruf pertama untuk pair forex/logam)."""
    s = ''.join((ch for ch in (symbol or '').upper() if ch.isalnum()))
    return s[:6] if len(s) >= 6 else s
def correlated_with(symbol: str) -> set[str]:
    """Pair lain yang berkorelasi dengan `symbol` (kosong bila tidak ada)."""
    base = base_symbol(symbol)
    out = set()
    for group in CORRELATED_GROUPS:
        if base in group:
            out |= group - {base}
    return out
@dataclass(frozen=True)
class External:
    """Keadaan di luar akun ini (dikirim Hub)."""
    other_exposure: int = 0
    halt: bool = False
    halt_reason: str = ''
    def to_dict(self) -> dict:
        return {'other_exposure': self.other_exposure, 'halt': self.halt, 'halt_reason': self.halt_reason}
    @staticmethod
    def from_dict(d: dict | None) -> 'External':
        d = d or {}
        return External(int(d.get('other_exposure') or 0), bool(d.get('halt')), str(d.get('halt_reason') or ''))
def check_entry(cfg: GovernorConfig, symbol: str, exposure_by_symbol: dict[str, int], external: External | None=None) -> tuple[bool, str]:
    """(boleh, kode alasan). Kode: \"\" | \"halt\" | \"max_positions\" | \"correlated:<SYMBOL>\".\n\n    `exposure_by_symbol` = posisi+pending KingAI per symbol di akun ini."""
    ext = external or External()
    if ext.halt:
        return (False, 'halt')
    else:
        total = sum(exposure_by_symbol.values()) + ext.other_exposure
        if total >= cfg.max_positions:
            return (False, 'max_positions')
        else:
            if cfg.block_correlated:
                mine = base_symbol(symbol)
                related = correlated_with(symbol)
                for sym, n in exposure_by_symbol.items():
                    if n > 0 and base_symbol(sym) != mine and (base_symbol(sym) in related):
                        return (False, f'correlated:{sym}')
            return (True, '')
def external_for(cfg: GovernorConfig, account_id: str, exposure_by_account: dict[str, int], daily_by_account: dict[str, float]) -> External:
    """`External` untuk satu akun dari ringkasan SEMUA akun."""
    other = sum((n for acc, n in exposure_by_account.items() if acc != account_id))
    daily = sum(daily_by_account.values())
    if cfg.max_daily_loss > 0 and daily <= -abs(cfg.max_daily_loss):
        return External(other, True, f'daily_loss:{daily:.2f}')
    else:
        return External(other, False, '')
def reason_text(code: str, tr) -> str:
    """Kode alasan -> kalimat (tr dilewatkan supaya modul ini bebas i18n)."""
    if code.startswith('correlated:'):
        return tr('king.govr_correlated', symbol=code.split(':', 1)[1])
    else:
        if code.startswith('daily_loss') or code == 'halt':
            return tr('king.govr_halt')
        else:
            return tr(f'king.govr_{code}') if code else ''