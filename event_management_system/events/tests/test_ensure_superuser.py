from io import StringIO
from unittest import mock

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase

from .factories import PASSWORD

ENV = {'DJANGO_SUPERUSER_USERNAME': 'boss', 'DJANGO_SUPERUSER_EMAIL': 'boss@example.com',
       'DJANGO_SUPERUSER_PASSWORD': 'a-Strong-pass-42'}


class EnsureSuperuserTests(TestCase):
    def run_command(self, env):
        out = StringIO()
        with mock.patch.dict('os.environ', env, clear=False):
            call_command('ensure_superuser', stdout=out)
        return out.getvalue()

    def test_creates_superuser(self):
        self.assertIn('Created superuser "boss"', self.run_command(ENV))
        user = User.objects.get(username='boss')
        self.assertTrue(user.is_superuser and user.is_staff)
        self.assertTrue(user.check_password('a-Strong-pass-42'))

    def test_existing_account_is_left_unchanged(self):
        User.objects.create_user('boss', password=PASSWORD)
        self.assertIn('already exists', self.run_command(ENV))
        user = User.objects.get(username='boss')
        self.assertFalse(user.is_superuser)
        self.assertTrue(user.check_password(PASSWORD))

    def test_skips_without_credentials(self):
        env = {'DJANGO_SUPERUSER_USERNAME': '', 'DJANGO_SUPERUSER_PASSWORD': ''}
        self.assertIn('skipping', self.run_command(env))
        self.assertFalse(User.objects.exists())
