# Decompiled with PyLingual (https://pylingual.io)
# Internal filename: 'kingai\\core\\secure_store.py'
# Bytecode version: 3.10.b1 (3439)
# Source timestamp: 1970-01-01 00:00:00 UTC (0)

"""\nsecure_store.py\n===============\nEnkripsi API key endpoint AI dengan Windows DPAPI (CryptProtectData) -\nhasil enkripsi hanya bisa dibuka oleh akun Windows yang sama di PC yang\nsama, jadi file data/ yang tersalin ke tempat lain tidak membocorkan key.\n\nKalau DPAPI tidak tersedia (bukan Windows), protect() mengembalikan \"\"\ndan key tidak disimpan sama sekali - lebih aman daripada menyimpan\nplaintext diam-diam.\n"""
import base64
import ctypes
from ctypes import wintypes
_PREFIX = 'dpapi:'
_CRYPTPROTECT_UI_FORBIDDEN = 1
class _Blob(ctypes.Structure):
    _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_char))]
def _blob_from(data: bytes):
    buf = ctypes.create_string_buffer(data, len(data))
    blob = _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    return (blob, buf)
def _call(func_name: str, data: bytes) -> bytes | None:
    # ***<module>._call: Failure: Different control flow
    try:
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
    except AttributeError:
        return None
    blob_in, _keep = _blob_from(data)
    blob_out = _Blob()
    try:
        func = getattr(crypt32, func_name)
        func.restype = wintypes.BOOL
        if func_name == 'CryptProtectData':
            func.argtypes = [
                ctypes.POINTER(_Blob), wintypes.LPCWSTR, ctypes.POINTER(_Blob),
                wintypes.LPVOID, wintypes.LPVOID, wintypes.DWORD,
                ctypes.POINTER(_Blob),
            ]
            ok = func(ctypes.byref(blob_in), None, None, None, None, _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(blob_out))
        elif func_name == 'CryptUnprotectData':
            func.argtypes = [
                ctypes.POINTER(_Blob), ctypes.POINTER(wintypes.LPWSTR),
                ctypes.POINTER(_Blob), wintypes.LPVOID, wintypes.LPVOID,
                wintypes.DWORD, ctypes.POINTER(_Blob),
            ]
            description = wintypes.LPWSTR()
            ok = func(ctypes.byref(blob_in), ctypes.byref(description), None, None, None, _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(blob_out))
            if description:
                kernel32.LocalFree(ctypes.cast(description, ctypes.c_void_p))
        else:
            return None
    except (AttributeError, OSError, TypeError, ctypes.ArgumentError):
        return None
    if not ok:
        return None
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(blob_out.pbData, ctypes.c_void_p))
def protect(text: str) -> str:
    if not text:
        return ''
    else:
        data = _call('CryptProtectData', text.encode('utf-8'))
        if data is None:
            return ''
        else:
            return _PREFIX + base64.b64encode(data).decode('ascii')
def unprotect(token: str) -> str:
    if not token or not token.startswith(_PREFIX):
        return ''
    else:
        try:
            raw = base64.b64decode(token[len(_PREFIX):])
        except ValueError:
            return ''
        data = _call('CryptUnprotectData', raw)
        if data is None:
            return ''
        else:
            try:
                return data.decode('utf-8')
            except UnicodeDecodeError:
                return ''