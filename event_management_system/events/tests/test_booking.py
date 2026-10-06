import threading
import time
from unittest import mock

from django.core.exceptions import ValidationError
from django.db import connection
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from ..models import Booking, Event, NotEnoughSeats
from .factories import make_event, make_user


class SeatAccountingTests(TestCase):
    def setUp(self):
        self.event = make_event(capacity=10)

    def test_empty_event_has_full_capacity(self):
        self.assertEqual(self.event.booked_seats(), 0)
        self.assertEqual(self.event.remaining_seats(), 10)

    def test_counts_tickets_across_users(self):
        self.event.book(make_user('alice'), 3)
        self.event.book(make_user('bob'), 4)
        self.assertEqual(self.event.booked_seats(), 7)
        self.assertEqual(self.event.remaining_seats(), 3)

    def test_ignores_other_events(self):
        make_event(capacity=50).book(make_user(), 20)
        self.assertEqual(self.event.remaining_seats(), 10)

    def test_can_book_exactly_remaining_seats(self):
        booking = self.event.book(make_user(), 10)
        self.assertEqual(booking.number_of_tickets, 10)
        self.assertEqual(self.event.remaining_seats(), 0)

    def test_cancelled_bookings_do_not_hold_seats(self):
        booking = self.event.book(make_user(), 4)
        booking.status = Booking.Status.CANCELLED
        booking.save()
        self.assertEqual(self.event.remaining_seats(), 10)

    def test_status_defaults_to_booked_and_rejects_unknown_values(self):
        booking = self.event.book(make_user(), 1)
        self.assertEqual(booking.status, Booking.Status.BOOKED)
        booking.status = 'Lost'
        with self.assertRaises(ValidationError):
            booking.full_clean()

    def test_cannot_book_more_than_remaining(self):
        self.event.book(make_user('alice'), 8)
        with self.assertRaises(NotEnoughSeats):
            self.event.book(make_user('bob'), 3)
        self.assertEqual(Booking.objects.count(), 1)


class BookEventViewTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.event = make_event(capacity=10)
        self.url = reverse('book_event', args=[self.event.id])

    def test_anonymous_redirected_to_login(self):
        response = self.client.get(self.url)
        self.assertRedirects(response, f"{reverse('login')}?next={self.url}")

    def test_missing_event_404(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse('book_event', args=[999])).status_code, 404)

    def test_get_shows_form(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertContains(response, 'name="number_of_tickets"')

    def test_successful_booking(self):
        self.client.force_login(self.user)
        response = self.client.post(self.url, {'number_of_tickets': 3})
        self.assertRedirects(response, reverse('my_bookings'))
        booking = Booking.objects.get()
        self.assertEqual((booking.user, booking.event, booking.number_of_tickets), (self.user, self.event, 3))
        self.assertEqual(booking.status, 'Booked')

    def test_too_many_tickets_rejected(self):
        self.event.book(make_user('bob'), 8)
        self.client.force_login(self.user)
        response = self.client.post(self.url, {'number_of_tickets': 3})
        self.assertContains(response, 'Not enough seats available!')
        self.assertFalse(Booking.objects.filter(user=self.user).exists())

    def test_full_event_closed(self):
        self.event.book(make_user('bob'), 10)
        self.client.force_login(self.user)
        for response in (self.client.get(self.url), self.client.post(self.url, {'number_of_tickets': 1})):
            self.assertContains(response, 'This event is full')
            self.assertNotContains(response, 'name="number_of_tickets"')
        self.assertFalse(Booking.objects.filter(user=self.user).exists())

    def test_invalid_ticket_count_shows_error(self):
        self.client.force_login(self.user)
        response = self.client.post(self.url, {'number_of_tickets': 0})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].errors)
        self.assertFalse(Booking.objects.exists())

    def test_negative_booking_cannot_free_seats(self):
        self.event.book(make_user('bob'), 10)
        self.client.force_login(self.user)
        self.client.post(self.url, {'number_of_tickets': -5})
        response = self.client.post(self.url, {'number_of_tickets': 3})
        self.assertEqual(Booking.objects.count(), 1)
        self.assertContains(response, 'This event is full')


class ConcurrentBookingTests(TransactionTestCase):
    """Two requests racing for the last seats must not overbook."""

    def test_simultaneous_bookings_cannot_exceed_capacity(self):
        event = make_event(capacity=10)
        users = [make_user(f'racer{i}') for i in range(2)]

        # Slow down the seat check so both threads are inside book() at once.
        original = Event.remaining_seats

        def slow_remaining_seats(self):
            seats = original(self)
            time.sleep(0.3)
            return seats

        barrier = threading.Barrier(len(users))
        results = []

        def attempt(user):
            try:
                barrier.wait()
                Event.objects.get(pk=event.pk).book(user, 6)
                results.append('booked')
            except NotEnoughSeats:
                results.append('rejected')
            except Exception as exc:
                results.append(exc)
            finally:
                connection.close()

        with mock.patch.object(Event, 'remaining_seats', slow_remaining_seats):
            threads = [threading.Thread(target=attempt, args=(u,)) for u in users]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        self.assertCountEqual(results, ['booked', 'rejected'])
        self.assertEqual(event.booked_seats(), 6)
