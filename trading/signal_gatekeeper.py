# Decompiled with PyLingual (https://pylingual.io)
# Internal filename: 'kingai\\trading\\signal_gatekeeper.py'
# Bytecode version: 3.10.b1 (3439)
# Source timestamp: 1970-01-01 00:00:00 UTC (0)

"""\nsignal_gatekeeper.py\n=====================\n\"Penjaga Gerbang\" - satu titik masuk untuk SETIAP sinyal yang mau\ndieksekusi jadi order sungguhan, dari sumber mana pun. Murni kode\nberbasis aturan, TIDAK pernah memanggil LLM - tugasnya cuma bilang\nya/tidak secepat dan semurah mungkin sebelum trade_executor dilibatkan.\n\nKenapa dipisah dari base_autotrade_page.py: guard checks (posisi sudah\nada, action valid, limit harian, dst) sebelumnya tercampur inline di\n`_on_signal_ready` - gampang lolos kalau ada sumber sinyal baru yang lupa\nmengulang pengecekan yang sama. Dipusatkan di sini supaya SETIAP sinyal,\ndari mana pun asalnya, wajib lewat gerbang yang sama sebelum menyentuh\n`trade_executor.open_market_order`/`open_pending_order`.\n\n`exclude_tickets` = ticket milik Trade Mini (berbagi MAGIC yang sama\ndengan Auto Trade, lihat catatan di trade_executor.py) - tanpa ini,\nposisi Trade Mini di symbol yang sama membuat gerbang selalu menolak\ndengan \"position_already_open\" padahal Auto Trade sendiri belum punya\nposisi apa pun.\n\nTidak menyimpan state MT5 sendiri - `admit()` bertanya langsung ke MT5\n(read-only, aman dipanggil dari thread mana pun mengikuti pola\ntrade_executor.py), supaya keputusan selalu berdasarkan kondisi TERKINI.\n"""
from trading import account_mode, trade_executor
VALID_ACTIONS = {'BUY', 'SELL'}
class SignalGatekeeper:
    """Stateless dari sisi MT5 (selalu tanya kondisi terkini) - satu\n    instance cukup dipakai ulang untuk semua sinyal sepanjang umur\n    halaman auto trade, tidak perlu dibuat baru per sinyal."""
    def admit(self, mt5_module, signal: dict, daily_limit_hit: bool, exclude_tickets: set[int] | None=None) -> tuple[bool, str]:
        """Return (diterima, alasan_tolak). alasan_tolak string kosong\n        kalau diterima. Tidak melempar exception untuk kondisi yang sudah\n        diantisipasi - pemanggil cukup cek boolean pertama."""
        # ***<module>.SignalGatekeeper.admit: Failure: Different control flow
        if mt5_module is None:
            return (False, 'mt5_not_connected')
        else:
            if daily_limit_hit:
                return (False, 'daily_limit_hit')
            else:
                action = signal.get('action')
                if action not in VALID_ACTIONS:
                    return (False, f'invalid_action:{action}')
                else:
                    symbol = signal.get('symbol')
                    if not symbol:
                        return (False, 'missing_symbol')
                    else:
                        entry_type = signal.get('entry_type')
                        entry = signal.get('entry')
                        if entry_type != 'MARKET' and (entry is None or entry <= 0):
                                return (False, 'invalid_entry_price')
                        sl = signal.get('sl')
                        tp = signal.get('tp')
                        if sl and tp and (action == 'BUY') and (sl >= tp):
                                        return (False, 'sl_tp_inverted')
                        if sl and tp and (action == 'SELL') and (sl <= tp):
                                        return (False, 'sl_tp_inverted')
                        tickets = exclude_tickets or set()
                        if not trade_executor.get_positions(mt5_module, symbol, tickets):
                            return (False, 'position_already_open')
                        else:
                            if account_mode.is_netting() and trade_executor.get_foreign_positions(mt5_module, symbol):
                                    return (False, 'netting_symbol_busy')
                            return (True, '')