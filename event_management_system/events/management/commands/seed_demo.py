from datetime import time, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from events.models import Event

# (name, days from today, start time, venue, capacity, price, description)
DEMO_EVENTS = [
    ('Campus Tech Fest', 7, time(10, 0), 'Main Auditorium', 150, Decimal('99'),
     'A day of talks, demos and hackathon finals from student and industry teams.'),
    ('Jazz Under the Stars', 10, time(19, 30), 'Open Air Theatre', 80, Decimal('350'),
     'An evening of live jazz with local bands. Bring a blanket.'),
    ('Python for Beginners Workshop', 14, time(14, 0), 'Computer Lab 3', 25, Decimal('0'),
     'Hands-on introduction to Python. Laptops provided. Free for all students.'),
    ('Startup Pitch Night', 18, time(18, 0), 'Innovation Hub', 60, Decimal('150'),
     'Ten founders, five minutes each, and a panel of investors.'),
    ('Photography Walk', 21, time(7, 0), 'City Botanical Garden', 3, Decimal('50'),
     'A small guided morning walk. Only 3 spots: book them all to try the waitlist.'),
    ('Charity Fun Run', 30, time(6, 30), 'Lakeside Park', 300, Decimal('200'),
     '5 km fun run; all proceeds go to the local children\'s hospital.'),
]


class Command(BaseCommand):
    help = 'Create future-dated demo events (safe to run more than once).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--organizer', help='Username to set as organizer (default: the first superuser, if any).',
        )

    def handle(self, *args, organizer=None, **options):
        if organizer:
            try:
                owner = User.objects.get(username=organizer)
            except User.DoesNotExist:
                raise CommandError(f'No user named "{organizer}".') from None
        else:
            owner = User.objects.filter(is_superuser=True).order_by('id').first()

        today = timezone.localdate()
        created = 0
        for name, days, start, venue, capacity, price, description in DEMO_EVENTS:
            _, was_created = Event.objects.get_or_create(
                event_name=name,
                is_cancelled=False,
                date__gte=today,
                defaults={
                    'date': today + timedelta(days=days), 'time': start, 'venue': venue,
                    'capacity': capacity, 'price': price, 'description': description, 'organizer': owner,
                },
            )
            created += was_created

        who = f' organized by {owner.username}' if owner else ''
        self.stdout.write(self.style.SUCCESS(
            f'Created {created} demo event(s){who}; {len(DEMO_EVENTS) - created} already existed.'
        ))
