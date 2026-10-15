"""Verify that the Windows binary and bundled ICO are both present."""
import ctypes
import sys
from pathlib import Path

from PIL import Image


def main():
    if sys.platform != "win32":
        raise RuntimeError("Windows only")
    executable = Path(sys.argv[1]).resolve()
    ico = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else executable.parent / "assets" / "spare_parts.ico"
    if not executable.is_file() or not ico.is_file():
        raise FileNotFoundError(f"EXEまたはアイコンが見つかりません: {executable}, {ico}")
    with Image.open(ico) as image:
        required = {(16, 16), (32, 32), (48, 48), (256, 256)}
        if not required.issubset(image.info.get("sizes", set())):
            raise ValueError("配布ICOの必要な解像度が不足しています")
    shell32 = ctypes.WinDLL("shell32")
    extract = shell32.ExtractIconExW
    extract.argtypes = [
        ctypes.c_wchar_p, ctypes.c_int,
        ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_void_p), ctypes.c_uint,
    ]
    extract.restype = ctypes.c_uint
    large = ctypes.c_void_p()
    small = ctypes.c_void_p()
    count = extract(str(executable), 0, ctypes.byref(large), ctypes.byref(small), 1)
    try:
        if not count or not large.value or not small.value:
            raise RuntimeError("EXE内にWindowsアイコンが埋め込まれていません")
    finally:
        user32 = ctypes.WinDLL("user32")
        for handle in (large, small):
            if handle.value:
                user32.DestroyIcon.argtypes = [ctypes.c_void_p]
                user32.DestroyIcon(handle)
    print(f"Windows EXE icon OK: {executable}")


if __name__ == "__main__":
    main()
