# Decompiled with PyLingual (https://pylingual.io)
# Internal filename: 'kingai\\engine\\distance_targets.py'
# Bytecode version: 3.10.b1 (3439)
# Source timestamp: 1970-01-01 00:00:00 UTC (0)

"""\ndistance_targets.py\n===================\nStatus satuan jarak (Point / Pips / % / ATR) untuk target \"Global\" dan tiap\nlane (pair). Form Pengaturan hanya menampilkan dan menulis ke sini; yang\ndisimpan ke disk dibaca lewat `global_values()` dan `lane_overrides()`.\n\nLane yang \"ikut global\" tidak punya penimpa (None). Setelah \"Ikuti global\"\ndimatikan, penimpa berdiri sendiri: disalin dari global saat itu dan tidak\nikut berubah bila global diubah. Murni Python (tanpa Qt/MT5).\n"""
from __future__ import annotations
from trading.settings import LANE_CONFIG_KEYS, UNIT_DEFAULTS
GLOBAL = 'global'
_UNIT_FIELDS = ('be_trigger', 'be_offset', 'trailing', 'max_drift', 'layer_distance', 'fixed_sl', 'fixed_tp', 'min_sl', 'min_tp')
def _subset(values: dict) -> dict:
    return {k: values[k] for k in LANE_CONFIG_KEYS if k in values}
class DistanceTargets:
    GLOBAL = GLOBAL
    def __init__(self, global_values: dict, lane_overrides: dict[str, dict | None]):
        self._global = _subset(global_values)
        self._lanes = {}
        self.current = GLOBAL
        self.sync_lanes(lane_overrides)
    def target_ids(self) -> list[str]:
        return [GLOBAL, *self._lanes]
    def follows_global(self, target: str) -> bool:
        return target == GLOBAL or self._lanes.get(target) is None
    def values(self, target: str | None=None) -> dict:
        """Nilai efektif target (kunci yang tak ada di penimpa jatuh ke global)."""
        target = target or self.current
        override = None if target == GLOBAL else self._lanes.get(target)
        return {**self._global, **(override or {})}
    def global_values(self) -> dict:
        return dict(self._global)
    def lane_overrides(self) -> dict[str, dict | None]:
        return {lane: dict(o) if o is not None else None for lane, o in self._lanes.items()}
    def select(self, target: str) -> None:
        self.current = target if target == GLOBAL or target in self._lanes else GLOBAL
    def set_follow_global(self, target: str, follow: bool) -> None:
        if target == GLOBAL or target not in self._lanes:
            return None
        else:
            if follow:
                self._lanes[target] = None
            else:
                if self._lanes[target] is None:
                    self._lanes[target] = dict(self._global)
    def update(self, values: dict, target: str | None=None) -> None:
        target = target or self.current
        if target == GLOBAL:
            self._global.update(_subset(values))
        else:
            if self._lanes.get(target) is not None:
                self._lanes[target].update(_subset(values))
    def change_unit(self, unit: str, target: str | None=None) -> None:
        """Ganti satuan: field jarak direset ke bawaan satuan (tidak dikonversi diam-diam)."""
        defaults = UNIT_DEFAULTS[unit]
        self.update({'distance_unit': unit, **{k: defaults[k] for k in _UNIT_FIELDS}}, target)
    def reset_manual_minimums(self) -> None:
        """Risiko preset -> Manual: SL/TP minimal semua target non-poin mulai dari bawaan satuannya\n        (nilai preset ada dalam poin, tidak boleh terbaca sebagai pips / % / ATR)."""
        for values in [self._global, *[o for o in self._lanes.values() if o is not None]]:
            unit = values.get('distance_unit')
            if unit and unit != 'points':
                    values['min_sl'], values['min_tp'] = (UNIT_DEFAULTS[unit]['min_sl'], UNIT_DEFAULTS[unit]['min_tp'])
    def restore_lane_overrides(self, lane_overrides: dict[str, dict | None]) -> None:
        """Pulihkan penimpa belum tersimpan (mis. setelah halaman dibangun ulang); lane tak dikenal diabaikan."""
        for lane, override in lane_overrides.items():
            if lane in self._lanes:
                self._lanes[lane] = dict(_subset(override)) if override else None
    def drop_lane(self, lane_id: str) -> None:
        self._lanes.pop(lane_id, None)
        if self.current == lane_id:
            self.current = GLOBAL
    def sync_lanes(self, lane_overrides: dict[str, dict | None]) -> None:
        """Samakan daftar lane: yang sudah dikenal dibiarkan (perubahan belum tersimpan tetap),\n        yang baru ditambahkan, yang hilang dibuang."""
        synced = {}
        for lane, override in lane_overrides.items():
            if lane in self._lanes:
                synced[lane] = self._lanes[lane]
            else:
                synced[lane] = dict(_subset(override)) if override else None
        self._lanes = synced
        if self.current != GLOBAL and self.current not in self._lanes:
                self.current = GLOBAL