"""SQLite is the only mandatory persistent file for the portable Onefile app."""
import os
import runpy
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = ROOT / "backend" / "config" / "settings.py"


def read_with_data_dir(directory):
    with patch.dict(os.environ, {"SPARES_DATA_DIR": str(directory)}):
        return runpy.run_path(str(SETTINGS))["SECRET_KEY"]


class SQLiteSecretTests(unittest.TestCase):
    def test_new_database_creates_and_reuses_secret_without_extra_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "test data"
            folder.mkdir()
            first = read_with_data_dir(folder)
            self.assertTrue(first)
            self.assertEqual(first, read_with_data_dir(folder))
            self.assertTrue((folder / "inventory.sqlite3").is_file())
            self.assertFalse((folder / ".django-secret").exists())
            with sqlite3.connect(folder / "inventory.sqlite3") as db:
                result = db.execute(
                    "SELECT value FROM spareparts_configuration "
                    "WHERE key = 'django_secret'"
                ).fetchone()
                self.assertEqual(result[0], first)

    def test_legacy_secret_is_transferred_to_database_without_replacement(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            legacy = folder / ".django-secret"
            legacy.write_text("legacy-secret-kept-for-portability", encoding="utf-8")
            self.assertEqual(
                read_with_data_dir(folder), "legacy-secret-kept-for-portability"
            )
            self.assertFalse(legacy.exists())
            self.assertEqual(
                read_with_data_dir(folder), "legacy-secret-kept-for-portability"
            )


if __name__ == "__main__":
    unittest.main()
