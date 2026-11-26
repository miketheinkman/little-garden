"""Hosted settings. The reverse proxy must replace the scheme header before forwarding."""
import os

from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.validators import DomainNameValidator, validate_email

from .common import *  # noqa: F403


def required(name):
    value = os.environ.get(name, "")
    if not value.strip():
        raise ImproperlyConfigured(f"Set {name} for the hosted application.")
    return value


if os.environ.get("GARDEN_DEV", "0") != "0" or os.environ.get("GARDEN_LOCAL_PILOT", "0") != "0":
    raise ImproperlyConfigured("Local pilot and development flags cannot be enabled in production.")

DEBUG = False
SECRET_KEY = required("GARDEN_SECRET_KEY")
if len(SECRET_KEY) < 50 or len(set(SECRET_KEY)) < 5 or SECRET_KEY.startswith("django-insecure-"):
    raise ImproperlyConfigured("Generate a random production GARDEN_SECRET_KEY of at least 50 characters.")

PUBLIC_HOST = required("GARDEN_PUBLIC_HOST")
try:
    DomainNameValidator(accept_idna=False)(PUBLIC_HOST)
except ValidationError:
    raise ImproperlyConfigured("GARDEN_PUBLIC_HOST must be a single DNS hostname.") from None

ALLOWED_HOSTS = [PUBLIC_HOST]
CSRF_TRUSTED_ORIGINS = [f"https://{PUBLIC_HOST}"]
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 3600  # Initially cover only this hostname during the alpha.
SECURE_REFERRER_POLICY = "same-origin"

DATABASES = {"default": {
    "ENGINE": "django.db.backends.postgresql",
    "HOST": required("GARDEN_DB_HOST"),
    "NAME": required("GARDEN_DB_NAME"),
    "USER": required("GARDEN_DB_USER"),
    "PASSWORD": required("GARDEN_DB_PASSWORD"),
    "CONN_MAX_AGE": 60,
    "CONN_HEALTH_CHECKS": True,
    "OPTIONS": {"connect_timeout": 5},
}}

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = required("GARDEN_SMTP_HOST")
try:
    EMAIL_PORT = int(os.environ.get("GARDEN_SMTP_PORT", "587"))
except ValueError:
    raise ImproperlyConfigured("GARDEN_SMTP_PORT must be a valid TCP port.") from None
if not 1 <= EMAIL_PORT <= 65535:
    raise ImproperlyConfigured("GARDEN_SMTP_PORT must be a valid TCP port.")
EMAIL_HOST_USER = required("GARDEN_SMTP_USER")
EMAIL_HOST_PASSWORD = required("GARDEN_SMTP_PASSWORD")
EMAIL_USE_TLS = True
EMAIL_TIMEOUT = 10
DEFAULT_FROM_EMAIL = required("GARDEN_FROM_EMAIL")
try:
    validate_email(DEFAULT_FROM_EMAIL)
except ValidationError:
    raise ImproperlyConfigured("GARDEN_FROM_EMAIL must be a sender email address.") from None

MIDDLEWARE = [*MIDDLEWARE[:1], "whitenoise.middleware.WhiteNoiseMiddleware", *MIDDLEWARE[1:]]
CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
    "coview": {"BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
               "LOCATION": "/tmp/little-garden-live", "OPTIONS": {"MAX_ENTRIES": 3000}},
}

STRIPE_TEST_ONE_TIME_LINK = STRIPE_TEST_MONTHLY_LINK = ""
