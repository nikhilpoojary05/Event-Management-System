import os

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        'Create a superuser from DJANGO_SUPERUSER_USERNAME / _EMAIL / _PASSWORD if it does not exist. '
        'Safe to run on every deploy: an existing account is never modified.'
    )

    def handle(self, *args, **options):
        username = os.environ.get('DJANGO_SUPERUSER_USERNAME', '').strip()
        password = os.environ.get('DJANGO_SUPERUSER_PASSWORD', '')
        email = os.environ.get('DJANGO_SUPERUSER_EMAIL', '').strip()

        if not username or not password:
            self.stdout.write('DJANGO_SUPERUSER_USERNAME/PASSWORD not set; skipping superuser creation.')
            return
        if User.objects.filter(username=username).exists():
            self.stdout.write(f'Superuser "{username}" already exists; leaving it unchanged.')
            return
        User.objects.create_superuser(username=username, email=email, password=password)
        self.stdout.write(self.style.SUCCESS(f'Created superuser "{username}".'))
