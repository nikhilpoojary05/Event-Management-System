import json
import os
import subprocess
import sys

from django.conf import settings
from django.test import SimpleTestCase

PRODUCTION_KEY = 'x7#Lq2!vR9@pZ4$wK8^mN3&bT6*yH1(cF5)jD0_gS-uE+aW=oI|eP~rU`lV<nQ>'


def run_settings(env, expr):
    """Load settings in a fresh interpreter with the given environment."""
    clean = {k: v for k, v in os.environ.items() if not k.startswith('DJANGO_')}
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

    def test_production_passes_deploy_checklist(self):
        clean = {k: v for k, v in os.environ.items() if not k.startswith('DJANGO_')}
        clean.update(DJANGO_DEBUG='False', DJANGO_SECRET_KEY=PRODUCTION_KEY, DJANGO_ALLOWED_HOSTS='example.com')
        result = subprocess.run(
            [sys.executable, 'manage.py', 'check', '--deploy', '--fail-level', 'WARNING'],
            cwd=settings.BASE_DIR, env=clean, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
