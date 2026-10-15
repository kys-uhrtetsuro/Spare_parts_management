"""The Windows taskbar and app window must use the same bundled native icon."""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("spare_parts_launcher", ROOT / "launcher.py")
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


class NativeIconTests(unittest.TestCase):
    def test_icon_is_sent_to_pywebview_before_window_is_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            icon = Path(tmp) / "assets" / "spare_parts.ico"
            icon.parent.mkdir(parents=True)
            icon.write_bytes(b"icon")
            webview = Mock()
            order = Mock()
            with patch.object(launcher, "set_windows_app_identity") as identity:
                order.attach_mock(identity, "identity")
                order.attach_mock(webview.create_window, "create_window")
                order.attach_mock(webview.start, "start")
                launcher.show_desktop(webview, "http://127.0.0.1:12345/", Path(tmp))
            webview.start.assert_called_once_with(gui="edgechromium", icon=str(icon))
            self.assertEqual(
                [call[0] for call in order.mock_calls],
                ["identity", "create_window", "start"],
            )

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
