"""Windows desktop entrypoint, Python 3.12 / Nuitka."""
import logging
import os
import socket
import sys
import threading
import time
import urllib.request
from pathlib import Path


def application_paths():
    # Nuitka onefile: __file__ is the temporary extraction folder;
    # sys.argv[0] is the original EXE path where persistent SQLite belongs.
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



APP_USER_MODEL_ID = "KYS.SparePartsManagement.Desktop"


def icon_path_for(resource_root):
    """Return the bundled icon. Never silently fall back to the Python icon."""
    icon = Path(resource_root) / "assets" / "spare_parts.ico"
    if not icon.is_file():
        raise FileNotFoundError(f"アプリアイコンが見つかりません: {icon}")
    return icon


def set_windows_app_identity():
    """Tell Windows the taskbar group identity before opening the native window."""
    if sys.platform != "win32":
        return
    import ctypes
    setter = ctypes.WinDLL("shell32").SetCurrentProcessExplicitAppUserModelID
    setter.argtypes = [ctypes.c_wchar_p]
    setter.restype = ctypes.c_long
    hresult = setter(APP_USER_MODEL_ID)
    if hresult != 0:
        raise OSError(f"Windowsタスクバーのアプリ識別子を設定できません: HRESULT {hresult:#x}")


def show_desktop(webview, url, resource_root):
    """pywebview 6.2 sets WinForms.Form.Icon before the native window is shown."""
    icon_path = icon_path_for(resource_root)
    set_windows_app_identity()
    webview.create_window(
        "予備品管理システム", url, width=1320, height=850, min_size=(900, 620)
    )
    webview.start(gui="edgechromium", icon=str(icon_path))


def main():
    app_root = application_paths()
    data_dir = app_root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    # A console-less Nuitka EXE must keep startup failures readable.
    startup_log = logging.getLogger("spares.startup")
    handler = logging.FileHandler(data_dir / "startup.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    startup_log.addHandler(handler)
    startup_log.setLevel(logging.INFO)
    startup_log.propagate = False
    instance_lock = None
    server = None
    try:
        startup_log.info("EXE起動・dataディレクトリ作成完了")
        instance_lock = single_instance(data_dir)
        startup_log.info("単一起動ロック取得完了")

        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
        startup_log.info("Django初期化開始")
        import django
        django.setup()
        startup_log.info("Django初期化完了")

        # Migrate BEFORE importing waitress or pywebview. A DB file should
        # exist even when the GUI stack fails to load.
        from django.core.management import call_command
        startup_log.info("SQLiteマイグレーション開始")
        call_command("migrate", interactive=False, verbosity=0)
        startup_log.info("SQLiteマイグレーション完了")

        startup_log.info("Waitress・pywebview読込開始")
        from django.core.wsgi import get_wsgi_application
        from waitress import create_server
        import webview
        startup_log.info("Waitress・pywebview読込完了")

        port = free_port()
        server = create_server(
            get_wsgi_application(), host="127.0.0.1", port=port, threads=4
        )
        threading.Thread(target=server.run, name="django-waitress", daemon=True).start()
        startup_log.info("ローカルサーバー起動・ヘルスチェック待機開始")
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

        startup_log.info("GUIウィンドウ起動開始")
        show_desktop(webview, url, Path(os.environ["SPARES_RESOURCE_DIR"]))
        startup_log.info("GUIウィンドウ正常終了")
    except BaseException:
        startup_log.exception("起動処理またはアプリ実行中に例外が発生")
        raise
    finally:
        if server is not None:
            server.close()
        if instance_lock is not None:
            instance_lock.close()
        startup_log.removeHandler(handler)
        handler.close()

if __name__ == "__main__":
    main()
