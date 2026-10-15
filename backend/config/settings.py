import os
from pathlib import Path

BASE_DIR = Path(os.environ.get("SPARES_RESOURCE_DIR", Path(__file__).resolve().parents[2])).resolve()
DATA_DIR = Path(os.environ.get("SPARES_DATA_DIR", BASE_DIR / "data")).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)

def load_secret_key():
    """Persist the stable per-installation Django secret inside the SQLite DB.

    This keeps SQLite as the only mandatory writable external application file.
    When upgrading from standalone, migrate the previous .django-secret value
    before deleting that legacy file.
    """
    import sqlite3

    from django.core.management.utils import get_random_secret_key

    legacy = DATA_DIR / ".django-secret"
    db = DATA_DIR / "inventory.sqlite3"
    with sqlite3.connect(db, timeout=20) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS spareparts_configuration "
            "(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        row = conn.execute(
            "SELECT value FROM spareparts_configuration WHERE key = 'django_secret'"
        ).fetchone()
        if row is None:
            existing_key = legacy.read_text(encoding="utf-8").strip() if legacy.is_file() else ""
            value = existing_key or get_random_secret_key()
            conn.execute(
                "INSERT OR IGNORE INTO spareparts_configuration (key, value) VALUES (?, ?)",
                ("django_secret", value),
            )
            conn.commit()
            row = conn.execute(
                "SELECT value FROM spareparts_configuration WHERE key = 'django_secret'"
            ).fetchone()
    if legacy.is_file():
        # The old value is now recoverable with the database's normal backups.
        try:
            legacy.unlink()
        except OSError:
            pass
    if not row or not row[0]:
        raise RuntimeError("SQLiteにDjango秘密鍵を保存できませんでした")
    return row[0]


SECRET_KEY = load_secret_key()

DEBUG = False
ALLOWED_HOSTS = ["127.0.0.1", "localhost", "testserver"]
INSTALLED_APPS = ["django.contrib.contenttypes", "inventory"]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
TEMPLATES = []
WSGI_APPLICATION = "config.wsgi.application"
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": DATA_DIR / "inventory.sqlite3",
        "OPTIONS": {"timeout": 20},
    }
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
TIME_ZONE = "Asia/Tokyo"
LANGUAGE_CODE = "ja"
CSRF_COOKIE_SAMESITE = "Strict"
CSRF_COOKIE_HTTPONLY = False
SESSION_COOKIE_SAMESITE = "Strict"
