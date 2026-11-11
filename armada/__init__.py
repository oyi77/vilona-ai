# Source Generated with Decompyle++
# File: __init__.pyc (Python 3.10)

'''
armada
======
Multi-pair + multi-akun MetaTrader 5 untuk Vilona AI.

    model.py      AccountSpec / LaneSpec / GovernorConfig + ArmadaStore (data/armada.json)
    governor.py   Risk Governor lintas lane (murni Python)
    protocol.py   format pesan JSON-lines Hub <-> worker
    worker.py     satu proses per terminal MT5 (host mesin Autotrade tiap lane)
    hub.py        sisi UI: mengelola worker, LaneProxy, agregasi armada

Alasan satu proses per terminal: package MetaTrader5 hanya bisa tersambung ke
SATU terminal per proses (mt5.initialize() berlaku global), jadi tiap akun
dijalankan worker sendiri; Hub (UI) tidak pernah menyentuh MT5 langsung.
'''
