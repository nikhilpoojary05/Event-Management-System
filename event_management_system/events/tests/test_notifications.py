from datetime import time, timedelta
from decimal import Decimal
from unittest import mock

from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from ..models import Booking, NotEnoughSeats
from .factories import PASSWORD, make_event, make_user


@override_settings(SITE_URL='https://events.example.com', DEFAULT_FROM_EMAIL='Events <noreply@example.com>')
class NotificationTestCase(TestCase):
    def setUp(self):
        self.organizer = make_user('org', can_add_events=True)
        self.event = make_event(
            event_name='AI & Future Tech', venue='Hall A', capacity=20, price=Decimal('250'),
            organizer=self.organizer, date=timezone.localdate() + timedelta(days=10), time=time(18, 30),
        )
        self.alice = make_user('alice')

    def book(self, user, tickets):
        with self.captureOnCommitCallbacks(execute=True):
            return self.event.book(user, tickets)


class BookingEmailTests(NotificationTestCase):
    def test_confirmation_sent_with_details(self):
        booking = self.book(self.alice, 3)
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, ['alice@example.com'])
        self.assertEqual(email.from_email, 'Events <noreply@example.com>')
        self.assertEqual(email.subject, 'Booking confirmed: AI & Future Tech')
        self.assertIn('Hi alice,', email.body)
        self.assertIn(f'Booking: #{booking.id}', email.body)
        self.assertIn('Tickets: 3 × ₹250.00', email.body)
        self.assertIn('Total:   ₹750.00', email.body)
        self.assertIn('Venue:   Hall A', email.body)
        self.assertIn('Time:    6:30 PM', email.body)
        self.assertIn(f'https://events.example.com/event/{self.event.id}/', email.body)
        self.assertIn('https://events.example.com/my-bookings/', email.body)

    def test_plain_text_is_not_html_escaped(self):
        self.book(self.alice, 1)
        body = mail.outbox[0].body
        self.assertIn('Event:   AI & Future Tech', body)
        self.assertNotIn('&amp;', body)

    def test_uses_full_name_when_available(self):
        self.alice.first_name, self.alice.last_name = 'Alice', 'Rao'
        self.alice.save()
        self.book(self.alice, 1)
        self.assertIn('Hi Alice Rao,', mail.outbox[0].body)

    def test_user_without_email_is_skipped(self):
        no_email = User.objects.create_user('ghost', password=PASSWORD)
        self.book(no_email, 1)
        self.assertEqual(mail.outbox, [])

    def test_nothing_sent_if_booking_fails(self):
        with self.captureOnCommitCallbacks(execute=True):
            with self.assertRaises(NotEnoughSeats):
                self.event.book(self.alice, 999)
        self.assertEqual(mail.outbox, [])

    def test_sent_only_after_commit(self):
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            self.event.book(self.alice, 1)
            self.assertEqual(mail.outbox, [])
        self.assertEqual(len(callbacks), 1)

    def test_mail_failure_is_logged_and_does_not_break_booking(self):
        self.client.force_login(self.alice)
        with mock.patch('events.notifications.send_mass_mail', side_effect=ConnectionRefusedError):
            with self.assertLogs('events.notifications', level='ERROR') as logs:
                with self.captureOnCommitCallbacks(execute=True):
                    response = self.client.post(reverse('book_event', args=[self.event.id]), {'number_of_tickets': 2})
        self.assertRedirects(response, reverse('my_bookings'))
        self.assertEqual(Booking.objects.filter(user=self.alice).count(), 1)
        self.assertIn('Failed to send 1 notification email(s)', logs.output[0])

    def test_booking_via_view_sends_confirmation(self):
        self.client.force_login(self.alice)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('book_event', args=[self.event.id]), {'number_of_tickets': 2})
        self.assertEqual([m.subject for m in mail.outbox], ['Booking confirmed: AI & Future Tech'])

    def test_user_cancelling_booking_gets_email(self):
        booking = self.book(self.alice, 2)
        mail.outbox.clear()
        self.client.force_login(self.alice)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('cancel_booking', args=[booking.id]))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, 'Booking cancelled: AI & Future Tech')
        self.assertIn(f'Your booking #{booking.id} for 2 ticket(s) has been cancelled', mail.outbox[0].body)

    def test_refused_cancellation_sends_nothing(self):
        booking = self.book(self.alice, 1)
        booking.cancel()
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            self.assertFalse(booking.cancel())
        self.assertEqual(mail.outbox, [])


class EventCancelledEmailTests(NotificationTestCase):
    def test_every_active_attendee_notified(self):
        bob = make_user('bob')
        self.book(self.alice, 2)
        self.book(bob, 1)
        earlier = self.book(make_user('carol'), 1)
        with self.captureOnCommitCallbacks(execute=True):
            earlier.cancel()
        mail.outbox.clear()

        self.client.force_login(self.organizer)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('cancel_event', args=[self.event.id]))

        self.assertEqual(sorted(m.to[0] for m in mail.outbox), ['alice@example.com', 'bob@example.com'])
        email = next(m for m in mail.outbox if m.to == ['alice@example.com'])
        self.assertEqual(email.subject, 'Event cancelled: AI & Future Tech')
        self.assertIn('2 ticket(s) (₹500.00) has been cancelled', email.body)
        self.assertIn('Please contact the organizer about a refund.', email.body)

    def test_free_event_cancellation_skips_refund_line(self):
        self.event.price = 0
        self.event.save()
        self.book(self.alice, 1)
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            self.event.cancel()
        self.assertNotIn('refund', mail.outbox[0].body)

    def test_admin_action_also_notifies(self):
        self.book(self.alice, 1)
        mail.outbox.clear()
        self.client.force_login(User.objects.create_superuser('root', 'root@example.com', PASSWORD))
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('admin:events_event_changelist'), {
                'action': 'cancel_events', '_selected_action': [self.event.pk],
            })
        self.assertEqual([m.to for m in mail.outbox], [['alice@example.com']])

    def test_event_without_bookings_sends_nothing(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.event.cancel()
        self.assertEqual(mail.outbox, [])


class EventUpdatedEmailTests(NotificationTestCase):
    def setUp(self):
        super().setUp()
        self.url = reverse('edit_event', args=[self.event.id])
        self.book(self.alice, 2)
        cancelled = self.book(make_user('dave'), 1)
        with self.captureOnCommitCallbacks(execute=True):
            cancelled.cancel()
        mail.outbox.clear()
        self.client.force_login(self.organizer)

    def edit(self, **overrides):
        data = {
            'event_name': self.event.event_name, 'description': self.event.description,
            'date': self.event.date.isoformat(), 'time': '18:30', 'venue': 'Hall A',
            'capacity': 20, 'price': '250',
        }
        data.update(overrides)
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(self.url, data)

    def test_venue_and_time_change_notifies_active_attendees(self):
        self.edit(venue='Rooftop', time='20:00')
        self.assertEqual([m.to for m in mail.outbox], [['alice@example.com']])
        body = mail.outbox[0].body
        self.assertEqual(mail.outbox[0].subject, 'Event updated: AI & Future Tech')
        self.assertIn('Time: 6:30 PM -> 8:00 PM', body)
        self.assertIn('Venue: Hall A -> Rooftop', body)
        self.assertNotIn('Date:', body.split('Updated details:')[0])
        self.assertIn('Venue:   Rooftop', body)

    def test_date_change_is_formatted(self):
        old_date = self.event.date
        new_date = old_date + timedelta(days=1)
        self.edit(date=new_date.isoformat())

        def readable(d):  # e.g. "Sunday, 18 October 2026"
            return f'{d:%A}, {d.day} {d:%B %Y}'

        self.assertIn(f'Date: {readable(old_date)} -> {readable(new_date)}', mail.outbox[0].body)

    def test_other_edits_do_not_notify(self):
        self.edit(description='New description', price='300', capacity=25, event_name='AI & Future Tech 2026')
        self.assertEqual(mail.outbox, [])

    def test_rejected_edit_does_not_notify(self):
        self.edit(venue='Rooftop', capacity=1)  # below the 2 seats booked
        self.assertEqual(mail.outbox, [])
        self.event.refresh_from_db()
        self.assertEqual(self.event.venue, 'Hall A')
