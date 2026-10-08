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


class EventAdminCancelActionTests(TestCase):
    def setUp(self):
        self.client.force_login(User.objects.create_superuser('root2', 'root2@example.com', PASSWORD))

    def test_cancel_action_cascades_to_bookings(self):
        event = make_event(event_name='Gala')
        booking = event.book(make_user('fan'), 2)
        response = self.client.post(reverse('admin:events_event_changelist'), {
            'action': 'cancel_events', '_selected_action': [event.pk],
        }, follow=True)
        self.assertContains(response, 'Cancelled 1 event(s) and 1 booking(s).')
        event.refresh_from_db()
        booking.refresh_from_db()
        self.assertTrue(event.is_cancelled)
        self.assertEqual(booking.status, Booking.Status.CANCELLED)

    def test_is_cancelled_not_editable_on_change_form(self):
        event = make_event()
        response = self.client.get(reverse('admin:events_event_change', args=[event.pk]))
        self.assertNotContains(response, 'name="is_cancelled"')
