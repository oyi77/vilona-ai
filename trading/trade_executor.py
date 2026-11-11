# Decompiled with PyLingual (https://pylingual.io)
# Internal filename: 'kingai\\trading\\trade_executor.py'
# Bytecode version: 3.10.b1 (3439)
# Source timestamp: 1970-01-01 00:00:00 UTC (0)

# ***<module>: Failure: Compilation Error
"""\ntrade_executor.py\n==================\nEksekusi & manajemen order trading LANGSUNG lewat package MetaTrader5,\ntanpa Expert Advisor/file bridge apapun - pengganti in-process untuk\n`autotrade_bridge.py` + seluruh logic `KingAutoTrade.mq5` (EA lama,\nsudah dihapus). Tiap fungsi publik di sini adalah port 1:1 dari fungsi\nMQL5 yang namanya disebut di docstring masing-masing - perilakunya\nsengaja dibuat identik, bukan didesain ulang, supaya hasil trading tidak\ndrift dari versi EA yang sudah terbukti jalan.\n\nSemua fungsi menerima `mt5_module` (modul MetaTrader5 yang sudah\nter-initialize) sebagai parameter pertama - pola yang sama dengan\n`trade_history.resolve_outcomes(mt5_module)` yang sudah lebih dulu\nmemanggil `mt5.history_deals_get()` langsung dari Python.\n\nPENTING soal thread: fungsi-fungsi yang MENGUBAH state (order_send,\nmodify SL/TP, close/cancel) HANYA boleh dipanggil dari main thread Qt\n(lewat QTimer manajemen posisi atau slot yang menerima sinyal dari\nscan-loop background thread lewat Qt Signal) - package MetaTrader5 tidak\ndijamin aman dipanggil bersamaan dari 2 thread untuk operasi yang\nmenulis order. Fungsi baca-saja (get_positions, get_pending_orders,\ncalc_daily_pl) aman dipanggil dari background thread, mengikuti pola\n`mt5_bridge.get_full_scan()` yang sudah established dipanggil dari\nscan-loop thread.\n"""
from datetime import datetime, timezone
from trading.trading_rules import DEVIATION_POINTS, is_autotrade_magic, magic_for
from core.i18n import tr
_FILLING_TRY_ORDER = ['IOC', 'FOK', 'RETURN']
_filling_cache: dict[str, str] = {}
_trailing_started: set[int] = set()
def _prune_trailing_state(active_tickets: set[int]) -> None:
    _trailing_started.intersection_update(active_tickets)
def get_server_time(mt5_module, symbol: str) -> datetime:
    """Waktu server MT5 saat ini, diambil dari tick terakhir symbol\n    (proxy - package MetaTrader5 tidak punya panggilan \'waktu server\n    sekarang\' langsung). Dipakai sebagai referensi batas hari untuk daily\n    P/L & reset harian supaya konsisten dengan zona waktu BROKER, bukan\n    waktu lokal komputer - sama seperti TimeCurrent() di EA lama."""
    tick = mt5_module.symbol_info_tick(symbol)
    if tick and tick.time:
        return datetime.fromtimestamp(tick.time, tz=timezone.utc)
    else:
        return datetime.now(timezone.utc)
def normalize_lot(mt5_module, symbol: str, lot: float) -> float:
    """Port NormalizeLot() - bulatkan ke volume_step, clamp ke volume_min/max."""
    info = mt5_module.symbol_info(symbol)
    if info is None:
        return lot
    else:
        step = info.volume_step or 0.01
        normalized = round(lot / step) * step
        normalized = max(info.volume_min, min(info.volume_max, normalized))
        return round(normalized, 2)
def _filling_const(mt5_module, name: str) -> int:
    return getattr(mt5_module, f'ORDER_FILLING_{name}')
def _send_market_with_filling_retry(mt5_module, symbol: str, base_request: dict):
    """Kirim order market, coba beberapa type_filling berurutan (cache\n    per symbol) sampai salah satu diterima broker. Berhenti retry kalau\n    kegagalan BUKAN karena filling mode (retcode 10030 =\n    TRADE_RETCODE_INVALID_FILL) - error lain (margin/stops/market\n    closed) tidak akan hilang cuma dengan ganti filling mode."""
    cached = _filling_cache.get(symbol)
    order = ([cached] if cached else []) + [m for m in _FILLING_TRY_ORDER if m != cached]
    last_result = None
    for mode_name in order:
        request = dict(base_request)
        request['type_filling'] = _filling_const(mt5_module, mode_name)
        result = mt5_module.order_send(request)
        last_result = result
        if result is not None and result.retcode == mt5_module.TRADE_RETCODE_DONE:
            _filling_cache[symbol] = mode_name
            return result
        else:
            if result is None or result.retcode != mt5_module.TRADE_RETCODE_INVALID_FILL:
                return result
    return last_result
def lot(symbol: str, action: str, lot: float, sl: float, tp: float, comment: str='', magic: int | None=None) -> None:
    pass
def open_market_order(mt5_module, symbol, action, lot, sl, tp, comment: str='', magic: int | None=None):
    """Port ExecuteSignal() jalur MARKET. Return (sukses, pesan, ticket).\n    `magic` None = magic pair ini (magic_for); diisi eksplisit oleh Connect Codex (MAGIC_CODEX)."""
    # ***<module>.open_market_order: Failure: Compilation Error
    magic = magic_for(symbol) if magic is None else magic
    lot = normalize_lot(mt5_module, symbol, lot)
    if lot <= 0:
        return (False, tr('exec.lot_invalid'), None)
    else:
        tick = mt5_module.symbol_info_tick(symbol)
        if tick is None:
            return (False, tr('exec.no_tick'), None)
        else:
            is_buy = action == 'BUY'
            price = tick.ask if is_buy else tick.bid
            order_type = mt5_module.ORDER_TYPE_BUY if is_buy else mt5_module.ORDER_TYPE_SELL
            request = {
                'action': mt5_module.TRADE_ACTION_DEAL,
                'symbol': symbol,
                'volume': lot,
                'type': order_type,
                'price': price,
                'sl': sl,
                'tp': tp,
                'deviation': 10,
                'magic': magic,
                'comment': comment,
                'type_time': mt5_module.ORDER_TIME_GTC,
            }
            result = _send_market_with_filling_retry(mt5_module, symbol, request)
def lot(placeholder, *, action: str, entry_type: str, lot: float, price: float, sl: float, tp: float, comment: str, magic: int | None) -> None:
    pass
def open_pending_order(mt5_module, symbol, action, entry_type, lot, price, sl, tp, comment: str='', magic: int | None=None):
    """Port ExecuteSignal() jalur STOP/LIMIT. `entry_type` \"STOP\" atau\n    \"LIMIT\". Return (sukses, pesan, ticket). `magic` None = magic pair ini."""
    # ***<module>.open_pending_order: Failure: Compilation Error
    magic = magic_for(symbol) if magic is None else magic
    lot = normalize_lot(mt5_module, symbol, lot)
    if lot <= 0:
        return (False, tr('exec.lot_invalid'), None)
    else:
        is_buy = action == 'BUY'
        if entry_type == 'STOP':
            order_type = mt5_module.ORDER_TYPE_BUY_STOP if is_buy else mt5_module.ORDER_TYPE_SELL_STOP
        else:
            order_type = mt5_module.ORDER_TYPE_BUY_LIMIT if is_buy else mt5_module.ORDER_TYPE_SELL_LIMIT
        request = {'action': mt5_module.TRADE_ACTION_PENDING, 'symbol': symbol, 'volume': lot, 'type': order_type, 'price': entry, 'sl': sl, 'tp': tp, 'deviation': 10, 'magic': magic, 'comment': comment, 'type_time': mt5_module.ORDER_TIME_GTC}
        result = mt5_module.order_send(request)
        return _order_result(mt5_module, result)
def _order_result(mt5_module, result) -> tuple[bool, str, int | None]:
    if result is None:
        return (False, tr('exec.order_failed', retcode='?', comment='order_send() returned None'), None)
    else:
        if result.retcode != mt5_module.TRADE_RETCODE_DONE:
            return (False, tr('exec.order_failed', retcode=result.retcode, comment=result.comment), None)
        else:
            return (True, tr('exec.order_sent', ticket=result.order), result.order)
def modify_position_sltp(mt5_module, ticket: int, symbol: str, sl: float, tp: float) -> tuple[bool, str]:
    """Port pola PositionModify() dipakai ManageBreakeven/ManageTrailingStop."""
    # ***<module>.modify_position_sltp: Failure: Compilation Error
    request = {'action': mt5_module.TRADE_ACTION_SLTP, 'position': ticket, 'symbol': symbol, 'sl': sl, 'tp': tp}
    result = mt5_module.order_send(request)
    if result is None or result.retcode != mt5_module.TRADE_RETCODE_DONE:
        return (False, result.comment if result else 'order_send() returned None')
    return (True, '')
def get_positions(mt5_module, symbol: str, exclude_tickets: set[int] | None=None) -> list:
    """Port CountOpenPositions() (dipakai juga untuk iterasi) - posisi\n    milik MAGIC ini saja untuk `symbol`.\n\n    `exclude_tickets` (BARU) - Trade Mini (trade_mini_panel.py) membuka\n    posisi dengan MAGIC yang SAMA dengan Auto Trade (tidak ada magic\n    number terpisah per fitur), jadi TANPA parameter ini, seluruh fungsi\n    manajemen Auto Trade (manage_breakeven, manage_trailing_stop, dst -\n    SEMUA berhilir dari get_positions ini) ikut menyentuh/menghitung posisi\n    Trade Mini walau checkbox BE/Trailing Trade Mini sendiri sedang mati -\n    bug yang dilaporkan user (\"uncheck BE/Trailing di Trade Mini tapi SL\n    tetap bergerak\", ternyata Auto Trade-lah yang menggerakkannya, bukan\n    Trade Mini). Pemanggil dari base_autotrade_page.py WAJIB mengirim\n    shell.trade_mini_panel.owned_tickets() di sini supaya posisi Trade\n    Mini benar-benar independen dari manajemen Auto Trade, sesuai\n    docstring trade_mini_panel.py sendiri. Default None (backward compat -\n    pemanggil lain, mis. Trade Mini/ScanPage, tidak perlu tahu soal\n    exclude_tickets sama sekali)."""
    positions = mt5_module.positions_get(symbol=symbol) or ()
    magic = magic_for(symbol)
    result = [p for p in positions if p.magic == magic]
    if exclude_tickets:
        result = [p for p in result if p.ticket not in exclude_tickets]
    return result
def get_foreign_positions(mt5_module, symbol: str) -> list:
    """Posisi di `symbol` yang BUKAN milik pair ini (EA lain, trade manual, magic lain).\n    Di akun NETTING order baru akan digabung ke posisi ini - Auto Trade wajib menahan entry."""
    magic = magic_for(symbol)
    return [p for p in mt5_module.positions_get(symbol=symbol) or () if p.magic != magic]
def get_pending_orders(mt5_module, symbol: str, exclude_tickets: set[int] | None=None) -> list:
    """Port CountPendingOrders() (dipakai juga untuk iterasi).\n    `exclude_tickets` - lihat catatan get_positions, alasan sama persis."""
    orders = mt5_module.orders_get(symbol=symbol) or ()
    magic = magic_for(symbol)
    result = [o for o in orders if o.magic == magic]
    if exclude_tickets:
        result = [o for o in result if o.ticket not in exclude_tickets]
    return result
def close_position(mt5_module, position) -> tuple[bool, str]:
    """Port PositionClose() - `position` adalah 1 elemen dari get_positions()."""
    # ***<module>.close_position: Failure: Compilation Error
    tick = mt5_module.symbol_info_tick(position.symbol)
    if tick is None:
        return (False, tr('exec.no_tick'))
    else:
        is_buy = position.type == mt5_module.POSITION_TYPE_BUY
        price = tick.bid if is_buy else tick.ask
        order_type = mt5_module.ORDER_TYPE_SELL if is_buy else mt5_module.ORDER_TYPE_BUY
        request = {'action': mt5_module.TRADE_ACTION_DEAL, 'symbol': position.symbol, 'volume': position.volume, 'type': order_type, 'position': position.ticket, 'price': price, 'deviation': 10, 'magic': getattr(position, 'magic', 0) or magic_for(position.symbol)}
        result = _send_market_with_filling_retry(mt5_module, position.symbol, request)
        if result is None or result.retcode != mt5_module.TRADE_RETCODE_DONE:
            retcode = result.retcode if result else '?'
            return (False, result.comment if result else 'order_send() returned None')
        return (True, '')
def cancel_order(mt5_module, ticket: int) -> tuple[bool, str]:
    """Port OrderDelete()."""
    # ***<module>.cancel_order: Failure: Compilation Error
    request = {'action': mt5_module.TRADE_ACTION_REMOVE, 'order': ticket}
    result = mt5_module.order_send(request)
    if result is None or result.retcode != mt5_module.TRADE_RETCODE_DONE:
        retcode = result.retcode if result else '?'
        return (False, result.comment if result else 'order_send() returned None')
    else:
        return (True, '')
def close_all(mt5_module, symbol: str) -> list[str]:
    """Port CloseAllPositionsAndOrders() - tutup semua posisi & batalkan\n    semua order pending MAGIC ini untuk `symbol`. Return list pesan log\n    (sudah diterjemahkan lewat tr()).\n\n    PERINGATAN: fungsi ini menutup SEMUA posisi/order MAGIC untuk `symbol`,\n    TERMASUK posisi yang dibuka Trade Mini (sama-sama pakai MAGIC yang\n    sama, lihat catatan di blok \"Trade Mini\" di bawah) - JANGAN dipakai\n    dari base_autotrade_page._stop_auto_trade lagi (bug lama: Stop Auto\n    Trade ikut menutup posisi Trade Mini yang seharusnya independen).\n    Auto Trade sekarang memakai close_all_excluding_tickets() supaya\n    posisi Trade Mini tidak tersentuh."""
    logs = []
    closed = 0
    for position in get_positions(mt5_module, symbol):
        ok, msg = close_position(mt5_module, position)
        if ok:
            closed += 1
        else:
            logs.append(tr('exec.close_position_failed', ticket=position.ticket, message=msg))
    cancelled = 0
    for order in get_pending_orders(mt5_module, symbol):
        ok, msg = cancel_order(mt5_module, order.ticket)
        if ok:
            cancelled += 1
        else:
            logs.append(tr('exec.cancel_order_failed', ticket=order.ticket, message=msg))
    logs.append(tr('exec.close_all_summary', closed=closed, cancelled=cancelled))
    return logs
def close_all_symbols_excluding_tickets(mt5_module, exclude_tickets: set[int]) -> list[str]:
    """Seperti close_all_excluding_tickets tapi lintas SEMUA symbol - tutup\n    tiap posisi & batalkan tiap pending order milik MAGIC ini apa pun\n    symbol-nya, kecuali ticket Trade Mini. Dipakai _stop_auto_trade:\n    symbol dikelola di Settings dan bisa diganti selagi auto trade\n    berjalan - posisi yang terbuka di symbol LAMA tidak boleh ditinggalkan\n    begitu saja saat STOP; varian yang di-scope 1 symbol tidak akan\n    melihatnya sama sekali."""
    logs = []
    closed = 0
    positions = mt5_module.positions_get() or ()
    for position in positions:
        if not is_autotrade_magic(position.magic) or position.ticket in exclude_tickets:
            continue
        else:
            ok, msg = close_position(mt5_module, position)
            if ok:
                closed += 1
            else:
                logs.append(tr('exec.close_position_failed', ticket=position.ticket, message=msg))
    cancelled = 0
    orders = mt5_module.orders_get() or ()
    for order in orders:
        if not is_autotrade_magic(order.magic) or order.ticket in exclude_tickets:
            continue
        else:
            ok, msg = cancel_order(mt5_module, order.ticket)
            if ok:
                cancelled += 1
            else:
                logs.append(tr('exec.cancel_order_failed', ticket=order.ticket, message=msg))
    logs.append(tr('exec.close_all_summary', closed=closed, cancelled=cancelled))
    return logs
def close_all_excluding_tickets(mt5_module, symbol: str, exclude_tickets: set[int]) -> list[str]:
    """Varian close_all() yang MENGECUALIKAN `exclude_tickets` - dipakai\n    base_autotrade_page._stop_auto_trade supaya menutup Auto Trade TIDAK\n    ikut menutup posisi/pending order yang dibuka Trade Mini (dilacak di\n    shell.trade_mini_panel._tickets), walau keduanya berbagi MAGIC yang\n    sama. Query MT5 langsung (bukan tracking manual sisi Auto Trade) -\n    lebih robust daripada Auto Trade melacak ticket sendiri (rawan lupa\n    di-update di banyak tempat) - \"milik Auto Trade\" didefinisikan sebagai\n    \"semua posisi MAGIC untuk symbol ini SELAIN yang diketahui milik Trade\n    Mini\"."""
    logs = []
    closed = 0
    for position in get_positions(mt5_module, symbol):
        if position.ticket in exclude_tickets:
            continue
        else:
            ok, msg = close_position(mt5_module, position)
            if ok:
                closed += 1
            else:
                logs.append(tr('exec.close_position_failed', ticket=position.ticket, message=msg))
    cancelled = 0
    for order in get_pending_orders(mt5_module, symbol):
        if order.ticket in exclude_tickets:
            continue
        else:
            ok, msg = cancel_order(mt5_module, order.ticket)
            if ok:
                cancelled += 1
            else:
                logs.append(tr('exec.cancel_order_failed', ticket=order.ticket, message=msg))
    logs.append(tr('exec.close_all_summary', closed=closed, cancelled=cancelled))
    return logs
def manage_breakeven(mt5_module, symbol: str, trigger_points: float, offset_points: float, exclude_tickets: set[int] | None=None) -> list[str]:
    """Port ManageBreakeven() - geser SL ke openPrice+offset sekali begitu\n    profit sudah melewati trigger (points). Return list pesan log.\n    `exclude_tickets` - lihat catatan get_positions (dipakai pemanggil Auto\n    Trade untuk mengecualikan posisi Trade Mini, sama MAGIC tapi harus\n    independen)."""
    logs = []
    if trigger_points <= 0:
        return logs
    else:
        info = mt5_module.symbol_info(symbol)
        tick = mt5_module.symbol_info_tick(symbol)
        if info is None or tick is None:
            return logs
        else:
            point, digits = (info.point, info.digits)
            for position in get_positions(mt5_module, symbol, exclude_tickets):
                open_price, cur_sl, cur_tp = (position.price_open, position.sl, position.tp)
                if position.type == mt5_module.POSITION_TYPE_BUY:
                    trigger = open_price + trigger_points * point
                    new_sl = round(open_price + offset_points * point, digits)
                    if tick.bid >= trigger and cur_sl < new_sl:
                            ok, _ = modify_position_sltp(mt5_module, position.ticket, symbol, new_sl, cur_tp)
                            if ok:
                                logs.append(tr('exec.be_applied', ticket=position.ticket, sl=new_sl))
                else:
                    trigger = open_price - trigger_points * point
                    new_sl = round(open_price - offset_points * point, digits)
                    if tick.ask <= trigger and (cur_sl == 0 or cur_sl > new_sl):
                            ok, _ = modify_position_sltp(mt5_module, position.ticket, symbol, new_sl, cur_tp)
                            if ok:
                                logs.append(tr('exec.be_applied', ticket=position.ticket, sl=new_sl))
            return logs
def manage_trailing_stop(mt5_module, symbol: str, trailing_points: float, be_trigger_points: float=0.0, exclude_tickets: set[int] | None=None) -> list[str]:
    """Port ManageTrailingStop() - geser SL mengikuti step (points), tidak\n    pernah mundur. Return list pesan log.\n\n    `be_trigger_points` - kalau BE aktif (>0), trailing BARU boleh mulai\n    menggeser SL SETELAH breakeven benar-benar sudah dieksekusi (SL sudah\n    dipindah manage_breakeven ke sisi profit dari open_price), BUKAN sejak\n    posisi dibuka. Tanpa guard ini, trailing (step kecil, mis. 100 poin)\n    dan BE (trigger lebih besar, mis. 300 poin) berjalan independen tiap\n    tick - trailing bisa lebih dulu menggeser SL ke dekat harga sekarang\n    jauh sebelum BE sempat trigger di levelnya sendiri, sehingga SL yang\n    muncul di posisi tidak pernah mencerminkan skenario \"BE dulu baru\n    trailing lanjut dari situ\" yang dijelaskan di autotrade.info_params_body.\n    Kalau BE tidak dipakai (be_trigger_points<=0), trailing tetap jalan\n    sejak awal seperti sebelumnya (tidak ada BE yang perlu ditunggu).\n    `exclude_tickets` - lihat catatan get_positions."""
    logs = []
    if trailing_points <= 0:
        return logs
    else:
        info = mt5_module.symbol_info(symbol)
        tick = mt5_module.symbol_info_tick(symbol)
        if info is None or tick is None:
            return logs
        else:
            point, digits = (info.point, info.digits)
            step = trailing_points * point
            active_tickets = set()
            for position in get_positions(mt5_module, symbol, exclude_tickets):
                active_tickets.add(position.ticket)
                cur_sl, cur_tp = (position.sl, position.tp)
                if be_trigger_points > 0:
                    if position.type == mt5_module.POSITION_TYPE_BUY:
                        if cur_sl < position.price_open:
                            continue
                    else:
                        if cur_sl == 0 or cur_sl > position.price_open:
                            continue
                if position.type == mt5_module.POSITION_TYPE_BUY:
                    new_sl = round(tick.bid - step, digits)
                    if new_sl > cur_sl and new_sl > position.price_open:
                            ok, _ = modify_position_sltp(mt5_module, position.ticket, symbol, new_sl, cur_tp)
                            if ok and position.ticket not in _trailing_started:
                                    _trailing_started.add(position.ticket)
                                    logs.append(tr('exec.trailing_applied', ticket=position.ticket, sl=new_sl))
                else:
                    new_sl = round(tick.ask + step, digits)
                    if (cur_sl == 0 or new_sl < cur_sl) and new_sl < position.price_open:
                            ok, _ = modify_position_sltp(mt5_module, position.ticket, symbol, new_sl, cur_tp)
                            if ok and position.ticket not in _trailing_started:
                                    _trailing_started.add(position.ticket)
                                    logs.append(tr('exec.trailing_applied', ticket=position.ticket, sl=new_sl))
            _prune_trailing_state(active_tickets)
            return logs
def get_be_trailing_status(mt5_module, symbol, exclude_tickets=tuple[bool, bool]):
    """(be_active, trailing_active) - status RIIL saat ini dari posisi\n    terbuka, BUKAN dari checkbox pengaturan. be_active True kalau MINIMAL\n    1 posisi terbuka SL-nya sudah berada di sisi PROFIT dari price_open\n    (breakeven sudah benar-benar dieksekusi, bukan cuma checkbox\n    \"Pakai BE\" dicentang) - kondisi ini PERSIS sama dengan guard di\n    manage_trailing_stop (baris \"BE belum dieksekusi... trailing menunggu\n    dulu\") supaya definisi \"BE aktif\" konsisten di kedua tempat.\n    trailing_active True kalau ada ticket di _trailing_started (SL sudah\n    pernah digeser trailing minimal sekali) yang posisinya MASIH terbuka\n    sekarang. Murni BACA (tidak memodifikasi apapun) - aman dipanggil\n    dari background thread mengikuti pola get_positions/calc_daily_pl,\n    dipakai DashboardPage untuk badge status ringkas (lihat\n    base_autotrade_page._manage_positions) menggantikan baris log\n    per-ticket exec.be_applied/exec.trailing_applied yang menumpuk kalau\n    banyak posisi kena bersamaan."""
    be_active = False
    trailing_active = False
    for position in get_positions(mt5_module, symbol, exclude_tickets):
        if position.sl != 0:
            if position.type == mt5_module.POSITION_TYPE_BUY and position.sl >= position.price_open:
                be_active = True
            else:
                if position.type == mt5_module.POSITION_TYPE_SELL and position.sl <= position.price_open:
                        be_active = True
        if position.ticket in _trailing_started:
            trailing_active = True
    return (be_active, trailing_active)
def get_positions_by_ticket(mt5_module, symbol: str, tickets: set[int]) -> list:
    """Subset get_positions(symbol) yang ticket-nya ada di `tickets` -\n    posisi yang sudah closed (ticket tidak ada lagi di positions_get)\n    otomatis tidak ikut, pemanggil (TradeMiniPanel) yang bertanggung\n    jawab membuang ticket closed dari set-nya sendiri kalau perlu."""
    if not tickets:
        return []
    else:
        return [p for p in mt5_module.positions_get(symbol=symbol) or () if p.ticket in tickets]
def manage_breakeven_tickets(mt5_module, symbol, tickets, trigger_points, offset_points=list[str]):
    """Varian manage_breakeven() dibatasi ke `tickets` saja (per-posisi)."""
    logs = []
    if trigger_points <= 0 or not tickets:
        return logs
    else:
        info = mt5_module.symbol_info(symbol)
        tick = mt5_module.symbol_info_tick(symbol)
        if info is None or tick is None:
            return logs
        else:
            point, digits = (info.point, info.digits)
            for position in get_positions_by_ticket(mt5_module, symbol, tickets):
                open_price, cur_sl, cur_tp = (position.price_open, position.sl, position.tp)
                if position.type == mt5_module.POSITION_TYPE_BUY:
                    trigger = open_price + trigger_points * point
                    new_sl = round(open_price + offset_points * point, digits)
                    if tick.bid >= trigger and cur_sl < new_sl:
                            ok, _ = modify_position_sltp(mt5_module, position.ticket, symbol, new_sl, cur_tp)
                            if ok:
                                logs.append(tr('exec.be_applied', ticket=position.ticket, sl=new_sl))
                else:
                    trigger = open_price - trigger_points * point
                    new_sl = round(open_price - offset_points * point, digits)
                    if tick.ask <= trigger and (cur_sl == 0 or cur_sl > new_sl):
                            ok, _ = modify_position_sltp(mt5_module, position.ticket, symbol, new_sl, cur_tp)
                            if ok:
                                logs.append(tr('exec.be_applied', ticket=position.ticket, sl=new_sl))
            return logs
def manage_trailing_stop_tickets(mt5_module, symbol, tickets, trailing_points, be_trigger_points=list[str]):
    """Varian manage_trailing_stop() dibatasi ke `tickets` saja, sama pola\n    BE-then-trailing (trailing menunggu BE selesai dulu kalau BE aktif)."""
    logs = []
    if trailing_points <= 0 or not tickets:
        return logs
    else:
        info = mt5_module.symbol_info(symbol)
        tick = mt5_module.symbol_info_tick(symbol)
        if info is None or tick is None:
            return logs
        else:
            point, digits = (info.point, info.digits)
            step = trailing_points * point
            for position in get_positions_by_ticket(mt5_module, symbol, tickets):
                cur_sl, cur_tp = (position.sl, position.tp)
                if be_trigger_points > 0:
                    if position.type == mt5_module.POSITION_TYPE_BUY:
                        if cur_sl < position.price_open:
                            continue
                    else:
                        if cur_sl == 0 or cur_sl > position.price_open:
                            continue
                if position.type == mt5_module.POSITION_TYPE_BUY:
                    new_sl = round(tick.bid - step, digits)
                    if new_sl > cur_sl and new_sl > position.price_open:
                            ok, _ = modify_position_sltp(mt5_module, position.ticket, symbol, new_sl, cur_tp)
                            if ok:
                                logs.append(tr('exec.trailing_applied', ticket=position.ticket, sl=new_sl))
                else:
                    new_sl = round(tick.ask + step, digits)
                    if (cur_sl == 0 or new_sl < cur_sl) and new_sl < position.price_open:
                            ok, _ = modify_position_sltp(mt5_module, position.ticket, symbol, new_sl, cur_tp)
                            if ok:
                                logs.append(tr('exec.trailing_applied', ticket=position.ticket, sl=new_sl))
            return logs
def close_positions_by_ticket(mt5_module, symbol: str, tickets: set[int]) -> list[str]:
    """Tutup hanya posisi yang ticket-nya ada di `tickets` - dipakai tombol\n    \'Close All Layer\' Trade Mini (tidak menyentuh posisi lain di symbol\n    yang sama)."""
    logs = []
    closed = 0
    for position in get_positions_by_ticket(mt5_module, symbol, tickets):
        ok, msg = close_position(mt5_module, position)
        if ok:
            closed += 1
        else:
            logs.append(tr('exec.close_position_failed', ticket=position.ticket, message=msg))
    logs.append(tr('exec.close_all_summary', closed=closed, cancelled=0))
    return logs
def cancel_drifted_pending(mt5_module, symbol: str, max_drift_points: float, exclude_tickets: set[int] | None=None, max_drift_candles: int=0, candle_tf: str='M15') -> list[str]:
    """Batalkan pending order (STOP/LIMIT) yang harga pasarnya sudah\n    menjauh >= max_drift_points dari harga entry order tsb, ATAU (kalau\n    max_drift_candles > 0) sudah menunggu >= max_drift_candles candle\n    `candle_tf` tanpa tersentuh - sama seperti Max Drift Backtest\n    (sim_broker._pending_drift, mode poin/candle/keduanya: batas yang\n    tidak dipakai dikirim 0). Dipanggil tiap tick manajemen posisi (sama\n    seperti manage_breakeven/manage_trailing_stop) supaya order usang\n    tidak menunggu tak terbatas. Setelah dibatalkan, tidak ada\n    posisi/pending terbuka lagi untuk symbol ini, jadi _scan_loop otomatis\n    minta sinyal AI baru di iterasi scan_interval berikutnya - tidak perlu\n    trigger scan instan terpisah. `point` dari symbol_info (bukan\n    10**-digits) supaya otomatis proporsional untuk broker 2-digit maupun\n    3-digit Gold. Umur dihitung dari candle yang BUKA sesudah\n    order.time_setup (keduanya waktu server MT5), jadi jeda weekend tidak\n    ikut terhitung. `exclude_tickets` - lihat catatan get_positions\n    (pending order Trade Mini, kalau ada, tidak boleh ikut dibatalkan\n    Auto Trade)."""
    # ***<module>.cancel_drifted_pending: Failure: Different bytecode
    logs = []
    if max_drift_points <= 0 and max_drift_candles <= 0:
        return logs
    else:
        info = mt5_module.symbol_info(symbol)
        tick = mt5_module.symbol_info_tick(symbol)
        if info is None or tick is None:
            return logs
        else:
            point = info.point
            orders = get_pending_orders(mt5_module, symbol, exclude_tickets)
            nth_open = None
            if max_drift_candles > 0 and orders:
                    timeframe = getattr(mt5_module, f'TIMEFRAME_{candle_tf}', None)
                    rates = mt5_module.copy_rates_from_pos(symbol, timeframe, 0, int(max_drift_candles)) if timeframe is not None else None
                    if rates is not None and len(rates) >= int(max_drift_candles):
                            nth_open = int(rates[0]['time'])
            for order in orders:
                is_buy_side = order.type in (mt5_module.ORDER_TYPE_BUY_STOP, mt5_module.ORDER_TYPE_BUY_LIMIT)
                current_price = tick.ask if is_buy_side else tick.bid
                drift_points = abs(current_price - order.price_open) / point
                by_pts = max_drift_points > 0 and drift_points >= max_drift_points
                by_age = nth_open is not None and nth_open > order.time_setup
                if not by_pts and (not by_age):
                        continue
                ok, _ = cancel_order(mt5_module, order.ticket)
                if not ok:
                    logs.append(tr('exec.pending_cancel_failed', ticket=order.ticket, drift=f'{drift_points:.0f}'))
                else:
                    if by_pts:
                        logs.append(tr('exec.pending_cancelled_drift', ticket=order.ticket, drift=f'{drift_points:.0f}'))
                    else:
                        logs.append(tr('exec.pending_cancelled_drift_candle', order.ticket))
                        int(max_drift_candles(candle_tf))
            return logs
def calc_daily_pl(mt5_module, symbol: str) -> tuple[float, int, int]:
    """Port CalcDailyPL() - P/L hari ini (server time, lihat\n    get_server_time) HANYA dari deal history yang sudah CLOSED\n    (DEAL_ENTRY_OUT) - TIDAK termasuk floating P/L posisi yang masih\n    terbuka (itu ditampilkan terpisah sebagai Floating P/L, lihat\n    base_autotrade_page.py) supaya Daily P/L murni mencerminkan\n    untung/rugi yang sudah direalisasikan hari ini, tidak naik-turun\n    mengikuti floating posisi yang belum ditutup. Return\n    (pl, wins, total_closed)."""
    now = get_server_time(mt5_module, symbol)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    deals = mt5_module.history_deals_get(day_start, now) or []
    magic = magic_for(symbol)
    wins = 0
    total_closed = 0
    pl = 0.0
    for d in deals:
        if d.symbol != symbol or d.magic != magic:
            continue
        else:
            if d.entry != mt5_module.DEAL_ENTRY_OUT:
                continue
            else:
                profit = d.profit + d.swap + d.commission
                pl += profit
                total_closed += 1
                if profit > 0:
                    wins += 1
    return (pl, wins, total_closed)
def get_closed_deals_today(mt5_module, symbol: str) -> list[tuple[int, float, int]]:
    """List (deal_ticket, profit_realized, position_id) untuk SEMUA deal\n    CLOSED (DEAL_ENTRY_OUT) hari ini punya bot ini (magic cocok) - dipakai\n    BaseAutoTradePage._manage_positions untuk mendeteksi deal BARU\n    (dibanding set ticket yang sudah pernah dilihat tick sebelumnya) dan\n    memicu AppState.notify_trade_closed(profit, strategy) supaya\n    Dashboard bisa menampilkan kilatan hijau/merah sesuai hasil di\n    klaster strategi terkait. profit_realized sudah termasuk\n    swap+commission, sama seperti perhitungan calc_daily_pl.\n    `position_id` (== ticket order pembuka posisi ini di MT5) dipakai\n    BaseAutoTradePage._ticket_strategy untuk lookup nama strategi yang\n    memicu order tersebut."""
    now = get_server_time(mt5_module, symbol)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    deals = mt5_module.history_deals_get(day_start, now) or []
    magic = magic_for(symbol)
    result = []
    for d in deals:
        if d.symbol != symbol or d.magic != magic:
            continue
        else:
            if d.entry != mt5_module.DEAL_ENTRY_OUT:
                continue
            else:
                result.append((d.ticket, d.profit + d.swap + d.commission, d.position_id))
    return result