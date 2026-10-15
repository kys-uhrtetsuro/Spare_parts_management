"""Windows desktop entrypoint, Python 3.12 / Nuitka."""
import os
import socket
import sys
import threading
import time
import urllib.request
from pathlib import Path


def application_paths():
    resource_root = Path(__file__).resolve().parent
    app_root = Path(sys.argv[0]).resolve().parent
    os.environ["SPARES_RESOURCE_DIR"] = str(resource_root)
    os.environ["SPARES_DATA_DIR"] = str(app_root / "data")
    sys.path.insert(0, str(resource_root / "backend"))
    return app_root


def single_instance(data_dir):
    if os.name != "nt":
        return None
    import msvcrt
    handle = open(data_dir / ".instance.lock", "a+b")
    handle.seek(0, 2)
    if handle.tell() == 0:
        handle.write(b"\0")
        handle.flush()
    handle.seek(0)
    try:
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        handle.close()
        raise RuntimeError("このフォルダの予備品管理システムは既に起動しています") from None
    return handle


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]



def set_windows_window_icon(icon_path):
    """Assign Windows small/big title-bar icons without pywebview internals."""
    if os.name != "nt" or not icon_path.is_file():
        return
    try:
        import ctypes
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
        user32.FindWindowW.restype = ctypes.c_void_p
        hwnd = user32.FindWindowW(None, "予備品管理システム")
        if not hwnd:
            return

        user32.LoadImageW.argtypes = [
            ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint,
            ctypes.c_int, ctypes.c_int, ctypes.c_uint,
        ]
        user32.LoadImageW.restype = ctypes.c_void_p
        user32.SendMessageW.argtypes = [
            ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_void_p,
        ]
        user32.SendMessageW.restype = ctypes.c_ssize_t
        for slot, size in ((0, 16), (1, 32)):
            # IMAGE_ICON=1, LR_LOADFROMFILE=0x10, WM_SETICON=0x80
            handle = user32.LoadImageW(None, str(icon_path), 1, size, size, 0x10)
            if handle:
                user32.SendMessageW(hwnd, 0x80, slot, handle)
    except OSError:
        # Cosmetic failure must never prevent the application from starting.
        pass


def main():
    app_root = application_paths()
    data_dir = app_root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    instance_lock = single_instance(data_dir)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django
    django.setup()
    from django.core.management import call_command
    from django.core.wsgi import get_wsgi_application
    from waitress import create_server
    import webview

    call_command("migrate", interactive=False, verbosity=0)
    port = free_port()
    server = create_server(
        get_wsgi_application(), host="127.0.0.1", port=port, threads=4
    )
    threading.Thread(target=server.run, name="django-waitress", daemon=True).start()
    url = f"http://127.0.0.1:{port}/"
    for _ in range(100):
        try:
            with urllib.request.urlopen(url + "api/health", timeout=0.2) as r:
                if r.status == 200:
                    break
        except (OSError, TimeoutError):
            time.sleep(0.05)
    else:
        raise RuntimeError("ローカルサーバーを起動できませんでした")

    try:
        window = webview.create_window(
            "予備品管理システム", url, width=1320, height=850, min_size=(900, 620)
        )
        window.events.shown += lambda: set_windows_window_icon(
            Path(os.environ["SPARES_RESOURCE_DIR"]) / "assets" / "spare_parts.ico"
        )
        webview.start(gui="edgechromium")
    finally:
        server.close()
        if instance_lock is not None:
            instance_lock.close()


if __name__ == "__main__":
    main()
