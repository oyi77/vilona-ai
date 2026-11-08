"""Vilona AI v2 - MT5 Bridge Module

Bridge to the running MetaTrader 5 terminal on the local machine.
Requires 'MetaTrader5' package and a running MT5 terminal.
"""

from pathlib import Path
import MetaTrader5 as mt5

MTF_TIMEFRAMES = {
    'M1': mt5.TIMEFRAME_M1,
    'M5': mt5.TIMEFRAME_M5,
    'M15': mt5.TIMEFRAME_M15,
    'M30': mt5.TIMEFRAME_M30,
    'H1': mt5.TIMEFRAME_H1,
    'H4': mt5.TIMEFRAME_H4,
    'D1': mt5.TIMEFRAME_D1
}

class MT5Bridge:
    """Wrapper around the official MetaTrader5 package."""
    
    def __init__(self):
        self._connected = False

    def connect(self, path=None):
        """Initialize connection to running MT5 terminal."""
        ok = mt5.initialize(path) if path else mt5.initialize()
        if not ok:
            code, desc = mt5.last_error()
            return (False, f"MT5 Connect Fail: {code} {desc}")
        
        self._connected = True
        info = mt5.terminal_info()
        acc = mt5.account_info()
        acc_txt = f"Login: {acc.login} Server: {acc.server}" if acc else ''
        return (True, f"MT5 Connected: {info.name} {acc_txt}")

    def terminal_exe_path(self):
        if not self._connected:
            return ''
        info = mt5.terminal_info()
        if info and getattr(info, 'path', ''):
            return str(Path(info.path) / 'terminal64.exe')
        return ''

    def disconnect(self):
        if self._connected:
            mt5.shutdown()
            self._connected = False

    def is_connected(self):
        return self._connected

    def check_alive(self):
        if not self._connected:
            return False
        if mt5.terminal_info() is None or mt5.account_info() is None:
            self._connected = False
        return self._connected

    def account_label(self):
        acc = mt5.account_info() if self._connected else None
        return str(acc.login) if acc else ''
