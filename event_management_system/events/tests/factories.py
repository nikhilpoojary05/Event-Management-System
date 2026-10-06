from datetime import time, timedelta

from django.contrib.auth.models import Permission, User
from django.utils import timezone

from ..models import Event

PASSWORD = 'pw-for-tests-123'


def make_event(**overrides):
    data = {
        'event_name': 'Tech Talk',
        'description': 'A talk',
        'date': timezone.localdate() + timedelta(days=7),
        'time': time(18, 0),
        'venue': 'Hall A',
        'capacity': 10,
        'price': 100,
    }
    data.update(overrides)
    return Event.objects.create(**data)


def make_user(username='alice', can_add_events=False):
    user = User.objects.create_user(username, email=f'{username}@example.com', password=PASSWORD)
    if can_add_events:
        user.user_permissions.add(Permission.objects.get(codename='add_event'))
    return user
