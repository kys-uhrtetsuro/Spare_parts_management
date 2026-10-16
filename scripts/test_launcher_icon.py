"""The Windows taskbar and app window must use the same bundled native icon."""
import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("spare_parts_launcher", ROOT / "launcher.py")
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


class NativeIconTests(unittest.TestCase):

    def test_onefile_paths_keep_sqlite_beside_original_executable(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            unpacked = root / "temporary" / "onefile-extraction"
            unpacked.mkdir(parents=True)
            binary = root / "portable" / "SparePartsManagement.exe"
            binary.parent.mkdir()
            old_file = launcher.__file__
            old_argv = list(launcher.sys.argv)
            old_env = {
                key: launcher.os.environ.get(key)
                for key in ("SPARES_RESOURCE_DIR", "SPARES_DATA_DIR", "SPARES_APP_ROOT")
            }
            old_sys_path = list(launcher.sys.path)
            try:
                launcher.os.environ.pop("SPARES_APP_ROOT", None)
                launcher.__file__ = str(unpacked / "launcher.py")
                launcher.sys.argv = [str(binary)]
                self.assertEqual(launcher.application_paths(), binary.parent)
                self.assertEqual(
                    Path(launcher.os.environ["SPARES_RESOURCE_DIR"]), unpacked
                )
                self.assertEqual(
                    Path(launcher.os.environ["SPARES_DATA_DIR"]),
                    binary.parent / "data",
                )
                db = binary.parent / "data" / "inventory.sqlite3"
                db.parent.mkdir()
                db.write_bytes(b"existing-sqlite-preserved")
                launcher.application_paths()
                self.assertEqual(db.read_bytes(), b"existing-sqlite-preserved")
            finally:
                launcher.__file__ = old_file
                launcher.sys.argv = old_argv
                launcher.sys.path[:] = old_sys_path
                for key, value in old_env.items():
                    if value is None:
                        launcher.os.environ.pop(key, None)
                    else:
                        launcher.os.environ[key] = value

    def test_native_launcher_keeps_existing_sqlite_beside_outer_exe(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "portable"
            resources = root / "src"
            resources.mkdir(parents=True)
            old_file, old_argv = launcher.__file__, list(launcher.sys.argv)
            old_path = list(launcher.sys.path)
            keys = ("SPARES_APP_ROOT", "SPARES_RESOURCE_DIR", "SPARES_DATA_DIR")
            old_env = {key: launcher.os.environ.get(key) for key in keys}
            try:
                launcher.__file__ = str(resources / "launcher.py")
                launcher.sys.argv = [str(resources / "SparePartsManagement.exe")]
                launcher.os.environ["SPARES_APP_ROOT"] = str(root)
                self.assertEqual(launcher.application_paths(), root)
                self.assertEqual(Path(launcher.os.environ["SPARES_RESOURCE_DIR"]), resources)
                self.assertEqual(Path(launcher.os.environ["SPARES_DATA_DIR"]), root / "data")
                db = root / "data" / "inventory.sqlite3"
                db.parent.mkdir()
                db.write_bytes(b"preserved")
                launcher.application_paths()
                self.assertEqual(db.read_bytes(), b"preserved")
                self.assertFalse((resources / "data").exists())
            finally:
                launcher.__file__, launcher.sys.argv = old_file, old_argv
                launcher.sys.path[:] = old_path
                for key, value in old_env.items():
                    if value is None:
                        launcher.os.environ.pop(key, None)
                    else:
                        launcher.os.environ[key] = value

    def test_database_migration_failure_is_written_to_startup_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            with (
                patch.object(launcher, "application_paths", return_value=directory),
                patch.object(launcher, "single_instance", return_value=None),
                patch("django.setup") as django_setup,
                patch("django.core.management.call_command",
                      side_effect=RuntimeError("migration-test-error")) as migrate,
            ):
                with self.assertRaisesRegex(RuntimeError, "migration-test-error"):
                    launcher.main()
            django_setup.assert_called_once_with()
            migrate.assert_called_once_with("migrate", interactive=False, verbosity=0)
            log = (directory / "data" / "startup.log").read_text(encoding="utf-8")
            self.assertIn("Django初期化完了", log)
            self.assertIn("SQLiteマイグレーション開始", log)
            self.assertNotIn("Waitress・pywebview読込開始", log)
            self.assertIn("RuntimeError: migration-test-error", log)
            self.assertFalse((directory / "data" / "inventory.sqlite3").exists())

    def test_icon_is_sent_to_pywebview_before_window_is_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            icon = Path(tmp) / "assets" / "spare_parts.ico"
            icon.parent.mkdir(parents=True)
            icon.write_bytes(b"icon")
            webview = Mock()
            webview.settings = {"ALLOW_DOWNLOADS": False}
            # The setting must be enabled before WebView2 creates the window.
            def assert_downloads_allowed(*_args, **_kwargs):
                self.assertTrue(webview.settings["ALLOW_DOWNLOADS"])
            webview.create_window.side_effect = assert_downloads_allowed
            order = Mock()
            with patch.object(launcher, "set_windows_app_identity") as identity:
                order.attach_mock(identity, "identity")
                order.attach_mock(webview.create_window, "create_window")
                order.attach_mock(webview.start, "start")
                launcher.show_desktop(webview, "http://127.0.0.1:12345/", Path(tmp))
            webview.start.assert_called_once_with(gui="edgechromium", icon=str(icon))
            self.assertIsInstance(
                webview.create_window.call_args.kwargs["js_api"],
                launcher.DesktopNotificationBridge,
            )
            self.assertEqual(
                [call[0] for call in order.mock_calls],
                ["identity", "create_window", "start"],
            )

    def test_native_low_stock_notification_bridge(self):
        fake = types.ModuleType("windows_toasts")
        fake.Toast = Mock(return_value=Mock())
        fake.WindowsToaster = Mock(return_value=Mock())
        with patch.object(launcher.sys, "platform", "win32"):
            with patch.dict(sys.modules, {"windows_toasts": fake}):
                bridge = launcher.DesktopNotificationBridge()
                self.assertFalse(bridge.notify_low_stock(0))
                self.assertFalse(bridge.notify_low_stock("1"))
                self.assertTrue(bridge.notify_low_stock(3))
        self.assertEqual(
            fake.Toast.return_value.text_fields,
            ["予備品管理システム：下限在庫",
             "3件の部品が下限値以下です。下限在庫一覧を確認してください。"],
        )
        fake.WindowsToaster.assert_called_once_with("予備品管理システム")
        fake.WindowsToaster.return_value.show_toast.assert_called_once_with(fake.Toast.return_value)

    def test_missing_icon_fails_without_opening_native_window(self):
        with tempfile.TemporaryDirectory() as tmp:
            webview = Mock()
            with self.assertRaisesRegex(FileNotFoundError, "アプリアイコン"):
                launcher.show_desktop(webview, "http://127.0.0.1:12345/", Path(tmp))
            webview.create_window.assert_not_called()
            webview.start.assert_not_called()

    def test_windows_app_user_model_id_is_set(self):
        import ctypes
        fake = Mock()
        fake.SetCurrentProcessExplicitAppUserModelID.return_value = 0
        with patch.object(launcher.sys, "platform", "win32"):
            with patch.object(ctypes, "WinDLL", return_value=fake, create=True):
                launcher.set_windows_app_identity()
        fake.SetCurrentProcessExplicitAppUserModelID.assert_called_once_with(
            launcher.APP_USER_MODEL_ID
        )

    def test_non_windows_does_not_attempt_windows_api(self):
        with patch.object(launcher.sys, "platform", "linux"):
            launcher.set_windows_app_identity()


if __name__ == "__main__":
    unittest.main()
