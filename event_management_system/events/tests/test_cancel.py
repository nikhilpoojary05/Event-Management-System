from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from ..models import Booking
from .factories import make_event, make_user


class CancelBookingModelTests(TestCase):
    def setUp(self):
        self.event = make_event(capacity=10)
        self.booking = self.event.book(make_user(), 4)

    def test_cancel_frees_seats(self):
        self.assertTrue(self.booking.cancel())
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.CANCELLED)
        self.assertEqual(self.event.remaining_seats(), 10)

    def test_cancel_twice_is_noop(self):
        self.booking.cancel()
        self.assertFalse(self.booking.cancel())

    def test_can_cancel_on_event_day(self):
        booking = make_event(date=timezone.localdate()).book(make_user('bob'), 1)
        self.assertTrue(booking.can_cancel)

    def test_cannot_cancel_past_event(self):
        past_event = make_event(capacity=10)
        booking = past_event.book(make_user('bob'), 2)
        past_event.date = timezone.localdate() - timedelta(days=1)
        past_event.save()
        booking.refresh_from_db()
        self.assertFalse(booking.can_cancel)
        self.assertFalse(booking.cancel())
        self.assertEqual(Booking.objects.get(pk=booking.pk).status, Booking.Status.BOOKED)

    def test_freed_seats_can_be_rebooked(self):
        self.event.book(make_user('bob'), 6)
        self.booking.cancel()
        self.event.book(make_user('carol'), 4)
        self.assertEqual(self.event.remaining_seats(), 0)


class CancelBookingViewTests(TestCase):
    def setUp(self):
        self.user = make_user('alice')
        self.event = make_event(event_name='Tech Talk', capacity=10)
        self.booking = self.event.book(self.user, 3)
        self.url = reverse('cancel_booking', args=[self.booking.id])

    def status(self):
        return Booking.objects.get(pk=self.booking.pk).status

    def test_owner_can_cancel(self):
        self.client.force_login(self.user)
        response = self.client.post(self.url, follow=True)
        self.assertRedirects(response, reverse('my_bookings'))
        self.assertContains(response, 'Your booking for Tech Talk has been cancelled.')
        self.assertEqual(self.status(), Booking.Status.CANCELLED)

    def test_cancelling_twice_shows_error(self):
        self.client.force_login(self.user)
        self.client.post(self.url)
        response = self.client.post(self.url, follow=True)
        self.assertContains(response, 'This booking can no longer be cancelled.')

    def test_get_not_allowed(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.assertEqual(self.status(), Booking.Status.BOOKED)

    def test_anonymous_redirected_to_login(self):
        response = self.client.post(self.url)
        self.assertRedirects(response, f"{reverse('login')}?next={self.url}", fetch_redirect_response=False)
        self.assertEqual(self.status(), Booking.Status.BOOKED)

    def test_other_user_gets_404(self):
        self.client.force_login(make_user('mallory'))
        self.assertEqual(self.client.post(self.url).status_code, 404)
        self.assertEqual(self.status(), Booking.Status.BOOKED)

    def test_missing_booking_404(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.post(reverse('cancel_booking', args=[999])).status_code, 404)

    def test_my_bookings_shows_cancel_button_only_when_allowed(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('my_bookings'))
        self.assertContains(response, self.url)
        self.assertContains(response, 'Cancel Booking')

        self.client.post(self.url)
        response = self.client.get(reverse('my_bookings'))
        self.assertNotContains(response, 'Cancel Booking')
        self.assertContains(response, 'Cancelled')
        self.assertContains(response, 'card-cancelled')

    def test_no_cancel_button_for_past_event(self):
        self.event.date = timezone.localdate() - timedelta(days=1)
        self.event.save()
        self.client.force_login(self.user)
        self.assertNotContains(self.client.get(reverse('my_bookings')), 'Cancel Booking')

    def test_full_event_reopens_after_cancel(self):
        self.event.book(make_user('bob'), 7)
        self.client.force_login(self.user)
        detail = reverse('event_detail', args=[self.event.id])
        self.assertContains(self.client.get(detail), 'Join Waitlist')
        self.client.post(self.url)
        self.assertContains(self.client.get(detail), 'Book Now')
