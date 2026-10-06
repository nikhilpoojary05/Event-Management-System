from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from ..models import Booking
from .factories import PASSWORD, make_event, make_user


class AdminTests(TestCase):
    def setUp(self):
        self.client.force_login(User.objects.create_superuser('root', 'root@example.com', PASSWORD))
        self.event = make_event(event_name='Tech Talk', capacity=10)
        self.event.book(make_user('alice'), 3)
        cancelled = self.event.book(make_user('bob'), 2)
        cancelled.status = Booking.Status.CANCELLED
        cancelled.save()

    def test_event_changelist_shows_seats_left(self):
        response = self.client.get(reverse('admin:events_event_changelist'))
        self.assertContains(response, 'Tech Talk')
        self.assertContains(response, '<td class="field-seats_left">7</td>', html=True)

    def test_booking_changelist_filters_by_status(self):
        url = reverse('admin:events_booking_changelist')
        self.assertContains(self.client.get(url), 'alice')
        response = self.client.get(url, {'status__exact': Booking.Status.CANCELLED})
        self.assertContains(response, 'bob')
        self.assertNotContains(response, 'alice')

    def test_search(self):
        response = self.client.get(reverse('admin:events_booking_changelist'), {'q': 'alice'})
        self.assertContains(response, 'alice')
        self.assertNotContains(response, '>bob<')
