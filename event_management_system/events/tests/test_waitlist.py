import threading
import time
from datetime import timedelta
from unittest import mock

from django.contrib.auth.models import User
from django.core import mail
from django.db import IntegrityError, connection, transaction
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from ..models import AlreadyWaitlisted, Booking, Event, EventCancelled, EventInPast, NotEnoughSeats, WaitlistEntry
from .factories import PASSWORD, make_event, make_user

Status = WaitlistEntry.Status


class WaitlistModelTests(TestCase):
    def setUp(self):
        self.event = make_event(event_name='Jazz Night', capacity=3)
        self.holders = [self.event.book(make_user(f'holder{i}'), 1) for i in range(3)]  # sold out

    def test_join_when_full_waits_in_line(self):
        first = self.event.join_waitlist(make_user('ann'), 1)
        second = self.event.join_waitlist(make_user('ben'), 2)
        self.assertEqual((first.status, first.position), (Status.WAITING, 1))
        self.assertEqual((second.status, second.position), (Status.WAITING, 2))

    def test_join_when_seats_free_books_immediately(self):
        self.holders[0].cancel()
        entry = self.event.join_waitlist(make_user('ann'), 1)
        self.assertEqual(entry.status, Status.BOOKED)
        self.assertEqual(entry.booking.number_of_tickets, 1)
        self.assertEqual(self.event.remaining_seats(), 0)

    def test_cannot_join_twice_but_can_rejoin_after_leaving(self):
        ann = make_user('ann')
        entry = self.event.join_waitlist(ann, 1)
        with self.assertRaises(AlreadyWaitlisted):
            self.event.join_waitlist(ann, 2)
        self.assertTrue(entry.leave())
        self.assertEqual(self.event.join_waitlist(ann, 2).status, Status.WAITING)

    def test_database_allows_only_one_waiting_entry_per_user(self):
        ann = make_user('ann')
        WaitlistEntry.objects.create(user=ann, event=self.event)
        with self.assertRaises(IntegrityError), transaction.atomic():
            WaitlistEntry.objects.create(user=ann, event=self.event)

    def test_cannot_join_cancelled_or_past_event(self):
        self.event.cancel()
        with self.assertRaises(EventCancelled):
            self.event.join_waitlist(make_user('ann'), 1)
        past = make_event(date=timezone.localdate() - timedelta(days=1))
        with self.assertRaises(EventInPast):
            past.join_waitlist(make_user('ben'), 1)

    def test_cancellation_promotes_in_order(self):
        ann = self.event.join_waitlist(make_user('ann'), 1)
        ben = self.event.join_waitlist(make_user('ben'), 1)
        self.holders[0].cancel()
        ann.refresh_from_db()
        ben.refresh_from_db()
        self.assertEqual(ann.status, Status.BOOKED)
        self.assertEqual(ben.status, Status.WAITING)
        self.assertEqual(ben.position, 1)

    def test_larger_request_keeps_its_place_while_smaller_one_fits(self):
        big = self.event.join_waitlist(make_user('big'), 2)
        small = self.event.join_waitlist(make_user('small'), 1)
        self.holders[0].cancel()  # one seat free
        big.refresh_from_db()
        small.refresh_from_db()
        self.assertEqual(small.status, Status.BOOKED)
        self.assertEqual((big.status, big.position), (Status.WAITING, 1))
        self.holders[1].cancel()
        self.holders[2].cancel()  # now two seats free
        big.refresh_from_db()
        self.assertEqual(big.status, Status.BOOKED)

    def test_promotion_uses_current_price(self):
        entry = self.event.join_waitlist(make_user('ann'), 2)
        self.event.price = 80
        self.event.save()
        self.holders[0].cancel()
        self.holders[1].cancel()
        entry.refresh_from_db()
        self.assertEqual(entry.booking.unit_price, 80)

    def test_no_promotion_for_cancelled_or_past_events(self):
        self.event.join_waitlist(make_user('ann'), 1)
        Event.objects.filter(pk=self.event.pk).update(date=timezone.localdate() - timedelta(days=1))
        Booking.objects.filter(pk=self.holders[0].pk).update(status=Booking.Status.CANCELLED)
        self.assertEqual(self.event.promote_waitlist(), [])

    def test_event_cancellation_closes_waitlist(self):
        entry = self.event.join_waitlist(make_user('ann'), 1)
        self.event.cancel()
        entry.refresh_from_db()
        self.assertEqual(entry.status, Status.EVENT_CANCELLED)

    def test_position_ignores_people_no_longer_waiting(self):
        first = self.event.join_waitlist(make_user('ann'), 1)
        second = self.event.join_waitlist(make_user('ben'), 1)
        first.leave()
        self.assertEqual(second.position, 1)
        self.assertFalse(first.leave())


class WaitlistEmailTests(TestCase):
    def setUp(self):
        self.event = make_event(event_name='Jazz Night', capacity=1, price=100)
        self.holder = self.event.book(make_user('holder'), 1)

    def test_promoted_user_gets_youre_in_email(self):
        ann = make_user('ann')
        self.event.join_waitlist(ann, 1)
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            self.holder.cancel()
        subjects = {m.to[0]: m.subject for m in mail.outbox}
        self.assertEqual(subjects['ann@example.com'], "You're in: Jazz Night")
        body = next(m.body for m in mail.outbox if m.to == ['ann@example.com'])
        self.assertIn("you're off the waitlist", body)
        self.assertIn('Total:   ₹100.00', body)

    def test_waiting_users_told_when_event_cancelled(self):
        self.event.join_waitlist(make_user('ann'), 1)
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            self.event.cancel()
        by_recipient = {m.to[0]: m for m in mail.outbox}
        self.assertEqual(set(by_recipient), {'holder@example.com', 'ann@example.com'})
        self.assertIn('You were on the waitlist for 1 ticket(s)', by_recipient['ann@example.com'].body)


class WaitlistViewTests(TestCase):
    def setUp(self):
        self.event = make_event(event_name='Jazz Night', capacity=2)
        self.event.book(make_user('holder'), 2)
        self.user = make_user('ann')
        self.join_url = reverse('join_waitlist', args=[self.event.id])
        self.book_url = reverse('book_event', args=[self.event.id])
        self.client.force_login(self.user)

    def test_full_event_booking_page_offers_waitlist(self):
        response = self.client.get(self.book_url)
        self.assertContains(response, 'This event is full.')
        self.assertContains(response, f'action="{self.join_url}"')
        self.assertContains(response, 'max="2"')

    def test_join_waitlist(self):
        response = self.client.post(self.join_url, {'number_of_tickets': 2}, follow=True)
        self.assertRedirects(response, reverse('my_bookings'))
        self.assertContains(response, "You&#x27;re #1 on the waitlist for Jazz Night.")
        self.assertContains(response, 'Position:</strong> #1 in line')
        entry = WaitlistEntry.objects.get(user=self.user)
        self.assertContains(response, reverse('leave_waitlist', args=[entry.id]))

    def test_join_rejects_more_than_capacity_or_zero(self):
        for tickets in (3, 0):
            response = self.client.post(self.join_url, {'number_of_tickets': tickets}, follow=True)
            self.assertRedirects(response, self.book_url)
        self.assertFalse(WaitlistEntry.objects.exists())

    def test_join_twice_shows_info(self):
        self.client.post(self.join_url, {'number_of_tickets': 1})
        response = self.client.post(self.join_url, {'number_of_tickets': 1}, follow=True)
        self.assertContains(response, 'already on the waitlist')
        self.assertEqual(WaitlistEntry.objects.count(), 1)

    def test_join_when_seat_just_freed_books_directly(self):
        Booking.objects.update(number_of_tickets=1)
        response = self.client.post(self.join_url, {'number_of_tickets': 1}, follow=True)
        self.assertContains(response, 'Seats were available, so we booked 1 ticket(s) for you.')
        self.assertTrue(Booking.objects.filter(user=self.user).exists())

    def test_join_cancelled_event(self):
        self.event.cancel()
        response = self.client.post(self.join_url, {'number_of_tickets': 1}, follow=True)
        self.assertContains(response, 'no longer taking bookings')

    def test_join_requires_post_and_login(self):
        self.assertEqual(self.client.get(self.join_url).status_code, 405)
        self.client.logout()
        self.assertRedirects(self.client.post(self.join_url, {'number_of_tickets': 1}),
                             f"{reverse('login')}?next={self.join_url}", fetch_redirect_response=False)

    def test_waiting_user_sees_position_on_booking_and_detail_pages(self):
        self.event.join_waitlist(make_user('first'), 1)
        self.client.post(self.join_url, {'number_of_tickets': 1})
        self.assertContains(self.client.get(self.book_url), '<strong>#2</strong>')
        detail = self.client.get(reverse('event_detail', args=[self.event.id]))
        self.assertContains(detail, "You're #2 on the waitlist.")
        self.assertContains(detail, '(2 on the waitlist)')

    def test_detail_offers_join_button_when_full(self):
        detail = self.client.get(reverse('event_detail', args=[self.event.id]))
        self.assertContains(detail, 'Join Waitlist')
        self.assertNotContains(detail, 'Book Now')

    def test_leave_waitlist(self):
        entry = self.event.join_waitlist(self.user, 1)
        response = self.client.post(reverse('leave_waitlist', args=[entry.id]), follow=True)
        self.assertContains(response, 'You have left the waitlist for Jazz Night.')
        entry.refresh_from_db()
        self.assertEqual(entry.status, Status.LEFT)
        response = self.client.post(reverse('leave_waitlist', args=[entry.id]), follow=True)
        self.assertContains(response, 'You are no longer on this waitlist.')

    def test_cannot_leave_someone_elses_entry(self):
        entry = self.event.join_waitlist(make_user('other'), 1)
        self.assertEqual(self.client.post(reverse('leave_waitlist', args=[entry.id])).status_code, 404)
        entry.refresh_from_db()
        self.assertEqual(entry.status, Status.WAITING)

    def test_only_waitlist_shows_on_my_bookings_without_empty_message(self):
        self.client.post(self.join_url, {'number_of_tickets': 1})
        response = self.client.get(reverse('my_bookings'))
        self.assertContains(response, 'Waitlist')
        self.assertNotContains(response, 'You have no bookings yet.')


class OrganizerWaitlistTests(TestCase):
    def setUp(self):
        self.organizer = make_user('org', can_add_events=True)
        self.event = make_event(event_name='Gala', organizer=self.organizer, capacity=2)
        self.event.book(make_user('holder'), 2)
        self.event.join_waitlist(make_user('ann'), 1)
        self.event.join_waitlist(make_user('ben'), 2)
        self.client.force_login(self.organizer)

    def test_attendees_page_lists_waitlist_in_order(self):
        response = self.client.get(reverse('event_attendees', args=[self.event.id]))
        self.assertContains(response, 'Waitlist (2)')
        body = response.content.decode()
        self.assertLess(body.index('ann@example.com'), body.index('ben@example.com'))

    def test_capacity_increase_promotes_waitlist(self):
        response = self.client.post(reverse('edit_event', args=[self.event.id]), {
            'event_name': 'Gala', 'description': 'A talk', 'date': self.event.date.isoformat(),
            'time': '18:00', 'venue': 'Hall A', 'capacity': 5, 'price': '100',
        }, follow=True)
        self.assertContains(response, '2 waitlisted booking(s) were confirmed.')
        self.assertFalse(self.event.waitlist_entries.filter(status=Status.WAITING).exists())
        self.event.refresh_from_db()
        self.assertEqual(self.event.remaining_seats(), 0)

    def test_admin_lists_entries_but_cannot_add(self):
        self.client.force_login(User.objects.create_superuser('root', 'root@example.com', PASSWORD))
        self.assertContains(self.client.get(reverse('admin:events_waitlistentry_changelist')), 'ann')
        self.assertEqual(self.client.get(reverse('admin:events_waitlistentry_add')).status_code, 403)


class ConcurrentWaitlistTests(TransactionTestCase):
    """A promotion and a direct booking racing for one freed seat must not overbook."""

    def test_freed_seat_goes_to_exactly_one_person(self):
        event = make_event(capacity=2)
        leaver = event.book(make_user('leaver'), 1)
        event.book(make_user('stayer'), 1)
        waiter = make_user('waiter')
        event.join_waitlist(waiter, 1)
        walk_in = make_user('walkin')

        original = Event.remaining_seats

        def slow_remaining_seats(self):
            seats = original(self)
            time.sleep(0.3)
            return seats

        barrier = threading.Barrier(2)
        errors = []

        def run(action):
            try:
                barrier.wait()
                action()
            except NotEnoughSeats:
                pass
            except Exception as exc:
                errors.append(exc)
            finally:
                connection.close()

        with mock.patch.object(Event, 'remaining_seats', slow_remaining_seats):
            threads = [
                threading.Thread(target=run, args=(lambda: Booking.objects.get(pk=leaver.pk).cancel(),)),
                threading.Thread(target=run, args=(lambda: Event.objects.get(pk=event.pk).book(walk_in, 1),)),
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        self.assertEqual(errors, [])
        self.assertLessEqual(event.booked_seats(), 2)
        got_seat = set(Booking.objects.filter(status=Booking.Status.BOOKED).values_list('user__username', flat=True))
        self.assertEqual(len(got_seat & {'waiter', 'walkin'}), 1)
