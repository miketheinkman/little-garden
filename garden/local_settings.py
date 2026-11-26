"""Local management, development server, and explicitly selected LAN pilot."""
import os
import secrets
from pathlib import Path

from .common import *  # noqa: F403

LOCAL_PILOT = os.getenv("GARDEN_LOCAL_PILOT") == "1"
DEBUG = not LOCAL_PILOT and os.getenv("GARDEN_DEV", "1") == "1"
SECRET_KEY = os.getenv("GARDEN_SECRET_KEY")
if not SECRET_KEY and (DEBUG or LOCAL_PILOT):
    secret_file = BASE_DIR / ".local-secret"
    if not secret_file.exists():
        try:
            with secret_file.open("x") as out:
                secret_file.chmod(0o600)
                out.write(secrets.token_urlsafe(64))
        except FileExistsError:
            pass
    SECRET_KEY = secret_file.read_text()
if not SECRET_KEY:
    raise RuntimeError("Set GARDEN_SECRET_KEY")
ALLOWED_HOSTS = os.getenv("GARDEN_HOSTS", "localhost,127.0.0.1,[::1]").split(",")
SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = not (DEBUG or LOCAL_PILOT)
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}


EMAIL_HOST = os.environ.get("GARDEN_SMTP_HOST", "")
EMAIL_PORT = int(os.environ.get("GARDEN_SMTP_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("GARDEN_SMTP_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("GARDEN_SMTP_PASSWORD", "")
EMAIL_USE_TLS = os.environ.get("GARDEN_SMTP_STARTTLS", "1") == "1"
EMAIL_TIMEOUT = 10
DEFAULT_FROM_EMAIL = os.environ.get("GARDEN_FROM_EMAIL", "garden@localhost")
EMAIL_FILE_PATH = BASE_DIR / ".private-mail"
GARDEN_GMAIL_FILE = EMAIL_FILE_PATH / "gmail.json"
EMAIL_BACKEND = (
    "django.core.mail.backends.smtp.EmailBackend" if EMAIL_HOST
    else "pilot.mail.LocalMailBackend"
)
if not EMAIL_HOST:
    EMAIL_FILE_PATH.mkdir(mode=0o700, exist_ok=True)
    EMAIL_FILE_PATH.chmod(0o700)

# Both pilot listeners share short-lived co-view frames through the user's runtime directory.
CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
    "coview": {
        "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
        "LOCATION": (Path(os.environ.get("XDG_RUNTIME_DIR", BASE_DIR)) if LOCAL_PILOT else BASE_DIR) / ".little-garden-live",
    },
}

STRIPE_TEST_ONE_TIME_LINK = os.environ.get("GARDEN_STRIPE_TEST_ONE_TIME_LINK", "").strip()
STRIPE_TEST_MONTHLY_LINK = os.environ.get("GARDEN_STRIPE_TEST_MONTHLY_LINK", "").strip()
