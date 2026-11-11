# Decompiled with PyLingual (https://pylingual.io)
# Internal filename: 'kingai\\armada\\protocol.py'
# Bytecode version: 3.10.b1 (3439)
# Source timestamp: 1970-01-01 00:00:00 UTC (0)

"""\nprotocol.py\n===========\nFormat pesan Hub <-> worker: satu objek JSON per baris (UTF-8) lewat stdin /\nstdout proses worker. stdout worker HANYA dipakai protokol ini (print()\nbiasa diarahkan ke stderr), jadi satu baris = satu pesan.\n\nHub -> worker\n    {\"t\": \"req\", \"id\": 7, \"op\": \"lane.start\", \"args\": {...}}\n\nWorker -> Hub\n    {\"t\": \"res\", \"id\": 7, \"ok\": true, \"data\": ..., \"error\": \"\"}     jawaban req\n    {\"t\": \"ev\", \"lane\": \"l1a2b3c\" | \"\", \"k\": \"log\", \"d\": {...}}     kejadian (lane \"\" = tingkat akun)\n    {\"t\": \"ready\", \"pid\": 1234, \"account\": \"main\"}                  worker siap menerima perintah\n\nMurni Python.\n"""
from __future__ import annotations
import json
import math
OP_CONNECT = 'connect'
OP_DISCONNECT = 'disconnect'
OP_SYMBOLS = 'symbols'
OP_SYNC = 'sync'
OP_RELOAD = 'reload'
OP_LANE_START = 'lane.start'
OP_LANE_STOP = 'lane.stop'
OP_GOVERNOR = 'governor'
OP_HISTORY = 'history'
OP_PROBE = 'probe'
OP_OPEN = 'open'
OP_VALIDATE = 'validate'
OP_PRICE = 'price'
OP_LICENSE = 'license'
OP_SHUTDOWN = 'shutdown'
EV_ACCOUNT = 'account'
EV_ACCT_STATS = 'acct'
EV_RUNNING = 'running'
EV_STATUS = 'status'
EV_LOG = 'log'
EV_STATS = 'stats'
EV_TICK = 'tick'
EV_TOKENS = 'tokens'
EV_MGMT = 'mgmt'
EV_SIGNAL = 'signal'
EV_PIPE = 'pipe'
EV_THINKING = 'thinking'
EV_ORDER = 'order'
EV_CLOSED = 'closed'
EV_GOV = 'gov'
EV_LICENSE = 'license'
def _clean(value):
    """JSON tidak mengenal NaN/Infinity - ganti None; set/tuple -> list."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    else:
        if isinstance(value, dict):
            return {str(k): _clean(v) for k, v in value.items()}
        else:
            if isinstance(value, (list, tuple, set)):
                return [_clean(v) for v in value]
            else:
                return value
def encode(message: dict) -> bytes:
    return (json.dumps(_clean(message), ensure_ascii=False, separators=(',', ':'), default=str) + '\n').encode('utf-8')
def decode(line: bytes | str) -> dict | None:
    """Satu baris -> pesan; baris rusak / bukan objek -> None (diabaikan)."""
    if isinstance(line, bytes):
        line = line.decode('utf-8', errors='replace')
    line = line.strip()
    if not line:
        return
    else:
        try:
            msg = json.loads(line)
        except ValueError:
            return None
        return msg if isinstance(msg, dict) and 't' in msg else None
def request(req_id: int, op: str, args: dict | None=None) -> bytes:
    return encode({'t': 'req', 'id': req_id, 'op': op, 'args': args or {}})
def response(req_id: int, ok: bool, data=None, error: str='') -> bytes:
    return encode({'t': 'res', 'id': req_id, 'ok': ok, 'data': data, 'error': error})
def event(lane: str, kind: str, data: dict | None=None) -> bytes:
    return encode({'t': 'ev', 'lane': lane, 'k': kind, 'd': data or {}})