import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("SPARES_DATA_DIR", BASE_DIR / "data")).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Local application: preserve the signing key across EXE upgrades.
key_file = DATA_DIR / ".django-secret"
if not key_file.exists():
    from django.core.management.utils import get_random_secret_key
    key_file.write_text(get_random_secret_key(), encoding="utf-8")
SECRET_KEY = key_file.read_text(encoding="utf-8").strip()

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
