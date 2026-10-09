import json
import os
import subprocess
import sys

from django.conf import settings
from django.test import SimpleTestCase

PRODUCTION_KEY = 'x7#Lq2!vR9@pZ4$wK8^mN3&bT6*yH1(cF5)jD0_gS-uE+aW=oI|eP~rU`lV<nQ>'


def _clean_environ():
    """The current environment minus anything that configures the app (e.g. CI's DATABASE_URL)."""
    app_vars = {'DATABASE_URL', 'RENDER_EXTERNAL_HOSTNAME'}
    return {k: v for k, v in os.environ.items() if not k.startswith('DJANGO_') and k not in app_vars}


def run_settings(env, expr):
    """Load settings in a fresh interpreter with the given environment."""
    clean = _clean_environ()
    clean.update(env, DJANGO_SETTINGS_MODULE='event_management_system.settings')
    code = (
        'import json, django; django.setup(); from django.conf import settings as s; '
        f'print(json.dumps({expr}))'
    )
    return subprocess.run(
        [sys.executable, '-c', code], cwd=settings.BASE_DIR, env=clean,
        capture_output=True, text=True,
    )


class SettingsFromEnvironmentTests(SimpleTestCase):
    def load(self, env, expr):
        result = run_settings(env, expr)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_local_defaults_need_no_configuration(self):
        debug, key, hosts = self.load({}, '[s.DEBUG, s.SECRET_KEY, s.ALLOWED_HOSTS]')
        self.assertTrue(debug)
        self.assertTrue(key.startswith('django-insecure-'))
        self.assertEqual(hosts, [])

    def test_production_requires_secret_key(self):
        result = run_settings({'DJANGO_DEBUG': 'False'}, 's.DEBUG')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('DJANGO_SECRET_KEY must be set', result.stderr)

    def test_production_reads_environment_and_enables_https_settings(self):
        values = self.load(
            {
                'DJANGO_DEBUG': 'false',
                'DJANGO_SECRET_KEY': PRODUCTION_KEY,
                'DJANGO_ALLOWED_HOSTS': 'example.com, www.example.com',
                'DJANGO_CSRF_TRUSTED_ORIGINS': 'https://example.com',
            },
            '[s.DEBUG, s.SECRET_KEY, s.ALLOWED_HOSTS, s.CSRF_TRUSTED_ORIGINS, '
            's.SESSION_COOKIE_SECURE, s.CSRF_COOKIE_SECURE, s.SECURE_SSL_REDIRECT, s.SECURE_HSTS_SECONDS > 0]',
        )
        self.assertEqual(values, [
            False, PRODUCTION_KEY, ['example.com', 'www.example.com'], ['https://example.com'],
            True, True, True, True,
        ])

    def test_email_prints_to_console_in_development(self):
        backend, site = self.load({}, '[s.EMAIL_BACKEND, s.SITE_URL]')
        self.assertEqual(backend, 'django.core.mail.backends.console.EmailBackend')
        self.assertEqual(site, 'http://127.0.0.1:8000')

    def test_email_uses_smtp_from_environment_in_production(self):
        values = self.load(
            {
                'DJANGO_DEBUG': 'False', 'DJANGO_SECRET_KEY': PRODUCTION_KEY,
                'DJANGO_EMAIL_HOST': 'smtp.example.com', 'DJANGO_EMAIL_PORT': '465',
                'DJANGO_EMAIL_HOST_USER': 'mailer', 'DJANGO_EMAIL_HOST_PASSWORD': 'secret',
                'DJANGO_EMAIL_USE_TLS': 'false', 'DJANGO_DEFAULT_FROM_EMAIL': 'Events <hi@example.com>',
                'DJANGO_SITE_URL': 'https://events.example.com/',
            },
            '[s.EMAIL_BACKEND, s.EMAIL_HOST, s.EMAIL_PORT, s.EMAIL_HOST_USER, s.EMAIL_HOST_PASSWORD, '
            's.EMAIL_USE_TLS, s.DEFAULT_FROM_EMAIL, s.SITE_URL]',
        )
        self.assertEqual(values, [
            'django.core.mail.backends.smtp.EmailBackend', 'smtp.example.com', 465, 'mailer', 'secret',
            False, 'Events <hi@example.com>', 'https://events.example.com',
        ])

    def test_sqlite_by_default_with_immediate_transactions(self):
        engine, mode = self.load({}, "[s.DATABASES['default']['ENGINE'], "
                                     "s.DATABASES['default']['OPTIONS']['transaction_mode']]")
        self.assertEqual((engine, mode), ('django.db.backends.sqlite3', 'IMMEDIATE'))

    def test_database_url_selects_postgres(self):
        db = self.load({'DATABASE_URL': 'postgres://app:pw@db.example.com:5432/events'},
                       "{k: s.DATABASES['default'][k] for k in ('ENGINE', 'NAME', 'HOST', 'PORT', 'CONN_MAX_AGE')}")
        self.assertEqual(db, {'ENGINE': 'django.db.backends.postgresql', 'NAME': 'events',
                              'HOST': 'db.example.com', 'PORT': 5432, 'CONN_MAX_AGE': 600})

    def test_whitenoise_and_production_storage_cache(self):
        dev = self.load({}, "[s.MIDDLEWARE[1], s.STORAGES['staticfiles']['BACKEND'], "
                            "s.CACHES['default']['BACKEND'] if hasattr(s, 'CACHES') else None]")
        self.assertEqual(dev[0], 'whitenoise.middleware.WhiteNoiseMiddleware')
        self.assertEqual(dev[1], 'django.contrib.staticfiles.storage.StaticFilesStorage')
        prod = self.load({'DJANGO_DEBUG': 'False', 'DJANGO_SECRET_KEY': PRODUCTION_KEY},
                         "[s.STORAGES['staticfiles']['BACKEND'], s.CACHES['default']['BACKEND']]")
        self.assertEqual(prod, ['whitenoise.storage.CompressedManifestStaticFilesStorage',
                                'django.core.cache.backends.db.DatabaseCache'])

    def test_render_hostname_is_trusted_automatically(self):
        values = self.load(
            {'DJANGO_DEBUG': 'False', 'DJANGO_SECRET_KEY': PRODUCTION_KEY,
             'RENDER_EXTERNAL_HOSTNAME': 'event-management.onrender.com'},
            '[s.ALLOWED_HOSTS, s.CSRF_TRUSTED_ORIGINS, s.SITE_URL]',
        )
        self.assertEqual(values, [['event-management.onrender.com'], ['https://event-management.onrender.com'],
                                  'https://event-management.onrender.com'])

    def test_production_without_smtp_prints_emails_to_logs(self):
        backend = self.load({'DJANGO_DEBUG': 'False', 'DJANGO_SECRET_KEY': PRODUCTION_KEY}, 's.EMAIL_BACKEND')
        self.assertEqual(backend, 'django.core.mail.backends.console.EmailBackend')

    def test_production_passes_deploy_checklist(self):
        clean = _clean_environ()
        clean.update(DJANGO_DEBUG='False', DJANGO_SECRET_KEY=PRODUCTION_KEY, DJANGO_ALLOWED_HOSTS='example.com')
        result = subprocess.run(
            [sys.executable, 'manage.py', 'check', '--deploy', '--fail-level', 'WARNING'],
            cwd=settings.BASE_DIR, env=clean, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
