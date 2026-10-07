from datetime import timedelta
from unittest import mock

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from ..models import Booking, Event, EventInPast
from .factories import make_event, make_user


def yesterday():
    return timezone.localdate() - timedelta(days=1)


class PastEventModelTests(TestCase):
    def test_is_past(self):
        self.assertTrue(make_event(date=yesterday()).is_past)
        self.assertFalse(make_event(date=timezone.localdate()).is_past)
        self.assertFalse(make_event().is_past)

    def test_cannot_book_past_event(self):
        event = make_event(date=yesterday())
        with self.assertRaises(EventInPast):
            event.book(make_user(), 1)
        self.assertFalse(Booking.objects.exists())

    def test_can_book_event_happening_today(self):
        make_event(date=timezone.localdate()).book(make_user(), 1)
        self.assertEqual(Booking.objects.count(), 1)


class PastEventViewTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.event = make_event(event_name='Old Show', date=yesterday())
        self.book_url = reverse('book_event', args=[self.event.id])

    def test_booking_page_closed(self):
        self.client.force_login(self.user)
        for response in (self.client.get(self.book_url), self.client.post(self.book_url, {'number_of_tickets': 1})):
            self.assertContains(response, 'This event has already taken place.')
            self.assertNotContains(response, 'name="number_of_tickets"')
        self.assertFalse(Booking.objects.exists())

    def test_event_ends_between_page_load_and_booking(self):
        # The view's own check passes, but the date rolls over before book() runs.
        self.event.date = timezone.localdate()
        self.event.save()
        self.client.force_login(self.user)
        with mock.patch.object(Event, 'is_past', new_callable=mock.PropertyMock, side_effect=[False, True]):
            response = self.client.post(self.book_url, {'number_of_tickets': 1})
        self.assertContains(response, 'This event has already taken place.')
        self.assertFalse(Booking.objects.exists())

    def test_detail_shows_event_ended(self):
        detail = reverse('event_detail', args=[self.event.id])
        for login in (False, True):
            with self.subTest(logged_in=login):
                if login:
                    self.client.force_login(self.user)
                response = self.client.get(detail)
                self.assertContains(response, 'Event Ended')
                self.assertNotContains(response, 'Book Now')
                self.assertNotContains(response, 'Login to Book')
