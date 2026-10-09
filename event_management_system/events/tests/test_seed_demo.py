from io import StringIO

from django.contrib.auth.models import User
from django.core.management import CommandError, call_command
from django.test import TestCase
from django.utils import timezone

from ..management.commands.seed_demo import DEMO_EVENTS
from ..models import Event
from .factories import PASSWORD, make_user


class SeedDemoTests(TestCase):
    def run_command(self, *args):
        out = StringIO()
        call_command('seed_demo', *args, stdout=out)
        return out.getvalue()

    def test_creates_future_events_owned_by_first_superuser(self):
        admin = User.objects.create_superuser('root', 'root@example.com', PASSWORD)
        output = self.run_command()
        self.assertIn(f'Created {len(DEMO_EVENTS)} demo event(s) organized by root', output)
        events = Event.objects.all()
        self.assertEqual(events.count(), len(DEMO_EVENTS))
        self.assertTrue(all(e.date > timezone.localdate() and e.organizer == admin for e in events))
        for event in events:
            event.full_clean()

    def test_is_idempotent(self):
        self.run_command()
        output = self.run_command()
        self.assertIn(f'Created 0 demo event(s); {len(DEMO_EVENTS)} already existed.', output)
        self.assertEqual(Event.objects.count(), len(DEMO_EVENTS))

    def test_organizer_option(self):
        org = make_user('org', can_add_events=True)
        self.run_command('--organizer', 'org')
        self.assertFalse(Event.objects.exclude(organizer=org).exists())
        with self.assertRaises(CommandError):
            self.run_command('--organizer', 'nobody')
