"""Production refuses incomplete configuration before opening a database or sending mail."""
import os
import runpy
from unittest import TestCase
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.core.management.utils import get_random_secret_key


class ProductionSettingsTests(TestCase):
    def setUp(self):
        self.env = {
            "GARDEN_PUBLIC_HOST": "alpha.example.org",
            "GARDEN_SECRET_KEY": get_random_secret_key(),
            "GARDEN_DB_HOST": "db", "GARDEN_DB_NAME": "little_garden",
            "GARDEN_DB_USER": "garden_app", "GARDEN_DB_PASSWORD": "test-only",
            "GARDEN_SMTP_HOST": "mail.example.org", "GARDEN_SMTP_USER": "mailer",
            "GARDEN_SMTP_PASSWORD": "test-only", "GARDEN_FROM_EMAIL": "garden@example.org",
        }

    def load(self, env):
        with patch.dict(os.environ, env, clear=True):
            return runpy.run_module("garden.settings")

    def test_missing_required_values(self):
        for key in self.env:
            with self.subTest(key=key), self.assertRaisesRegex(ImproperlyConfigured, key):
                self.load({k: v for k, v in self.env.items() if k != key})

    def test_reject_local_flags_and_invalid_settings(self):
        for key, value in [
            ("GARDEN_DEV", "1"), ("GARDEN_LOCAL_PILOT", "1"), ("GARDEN_SECRET_KEY", "too-short"),
            ("GARDEN_PUBLIC_HOST", "*"), ("GARDEN_PUBLIC_HOST", "https://alpha.example.org"),
            ("GARDEN_FROM_EMAIL", "missing-domain"), ("GARDEN_SMTP_PORT", "0"), ("GARDEN_SMTP_PORT", "abc"),
        ]:
            with self.subTest(key=key), self.assertRaises(ImproperlyConfigured):
                self.load({**self.env, key: value})

    def test_hosted_profile(self):
        settings = self.load(self.env)
        self.assertFalse(settings["DEBUG"])
        self.assertTrue(settings["SESSION_COOKIE_SECURE"] and settings["CSRF_COOKIE_SECURE"])
        self.assertEqual(settings["ALLOWED_HOSTS"], ["alpha.example.org"])
        self.assertTrue(settings["SECURE_SSL_REDIRECT"] and settings["EMAIL_USE_TLS"])
        self.assertEqual(settings["DATABASES"]["default"]["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual(settings["EMAIL_BACKEND"], "django.core.mail.backends.smtp.EmailBackend")
