"""Deploy-glue checks: local SQLite default and Dokku MySQL DATABASE_URL."""

import dj_database_url
from django.conf import settings
from django.test import SimpleTestCase


class DeploySettingsTests(SimpleTestCase):
    def test_local_default_is_sqlite(self):
        db = settings.DATABASES["default"]
        self.assertEqual(db["ENGINE"], "django.db.backends.sqlite3")
        self.assertTrue(str(db["NAME"]).endswith("db.sqlite3"))

    def test_mysql_database_url_parses_for_dokku(self):
        parsed = dj_database_url.parse(
            "mysql://demo:s3cret@mysql.internal:3306/trustsexample1"
        )
        self.assertEqual(parsed["ENGINE"], "django.db.backends.mysql")
        self.assertEqual(parsed["NAME"], "trustsexample1")
        self.assertEqual(parsed["USER"], "demo")
        self.assertEqual(parsed["HOST"], "mysql.internal")
        self.assertEqual(int(parsed["PORT"]), 3306)

    def test_whitenoise_is_enabled(self):
        self.assertIn(
            "whitenoise.middleware.WhiteNoiseMiddleware",
            settings.MIDDLEWARE,
        )
        security_at = settings.MIDDLEWARE.index(
            "django.middleware.security.SecurityMiddleware"
        )
        whitenoise_at = settings.MIDDLEWARE.index(
            "whitenoise.middleware.WhiteNoiseMiddleware"
        )
        self.assertEqual(whitenoise_at, security_at + 1)
