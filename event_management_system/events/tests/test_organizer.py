from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import AnonymousUser, Permission, User
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from ..models import Booking, Event, EventCancelled
from .factories import PASSWORD, make_event, make_user


def make_admin(username='boss'):
    """A non-superuser who can manage every event via the change_event permission."""
    user = make_user(username)
    user.user_permissions.add(Permission.objects.get(codename='change_event'))
    return User.objects.get(pk=user.pk)  # fresh instance: permission cache is per object


class OrganizerModelTests(TestCase):
    def setUp(self):
        self.organizer = make_user('org', can_add_events=True)
        self.event = make_event(organizer=self.organizer, capacity=20, price=Decimal('100'))

    def test_can_manage(self):
        self.assertTrue(self.event.can_manage(self.organizer))
        self.assertFalse(self.event.can_manage(make_user('other', can_add_events=True)))
        self.assertFalse(self.event.can_manage(AnonymousUser()))
        self.assertTrue(self.event.can_manage(make_admin()))
        self.assertTrue(self.event.can_manage(User.objects.create_superuser('root', 'r@example.com', PASSWORD)))

    def test_event_without_organizer_is_admin_only(self):
        orphan = make_event()
        self.assertFalse(orphan.can_manage(self.organizer))
        self.assertTrue(orphan.can_manage(make_admin()))

    def test_cancel_cancels_active_bookings_only(self):
        self.event.book(make_user('a'), 3)
        self.event.book(make_user('b'), 2)
        self.event.book(make_user('c'), 1).cancel()
        self.assertEqual(self.event.cancel(), 2)
        self.event.refresh_from_db()
        self.assertTrue(self.event.is_cancelled)
        self.assertFalse(self.event.booking_set.filter(status=Booking.Status.BOOKED).exists())

    def test_cancel_is_idempotent_and_skips_past_events(self):
        self.event.cancel()
        self.assertEqual(self.event.cancel(), 0)
        past = make_event(date=timezone.localdate() - timedelta(days=1))
        self.assertEqual(past.cancel(), 0)
        past.refresh_from_db()
        self.assertFalse(past.is_cancelled)

    def test_cannot_book_cancelled_event(self):
        self.event.cancel()
        with self.assertRaises(EventCancelled):
            self.event.book(make_user('late'), 1)

    def test_revenue_and_seat_counts_together(self):
        self.event.book(make_user('a'), 3)
        self.event.book(make_user('b'), 2)
        self.event.book(make_user('c'), 4).cancel()
        self.event.price = Decimal('999')  # later price change must not affect revenue
        self.event.save()
        annotated = Event.objects.with_seat_counts().with_revenue().get(pk=self.event.pk)
        self.assertEqual(annotated.booked_count, 5)
        self.assertEqual(annotated.seats_left, 15)
        self.assertEqual(annotated.revenue, Decimal('500.00'))

    def test_unsold_paid_event_shows_zero_revenue_not_free(self):
        self.client.force_login(self.organizer)
        response = self.client.get(reverse('my_events'))
        self.assertContains(response, '<td class="num">₹0.00</td>', html=True)

    def test_revenue_zero_without_bookings(self):
        self.assertEqual(Event.objects.with_revenue().get(pk=self.event.pk).revenue, Decimal('0'))


class AddEventSetsOrganizerTests(TestCase):
    def test_creator_becomes_organizer(self):
        organizer = make_user('org', can_add_events=True)
        self.client.force_login(organizer)
        self.client.post(reverse('add_event'), {
            'event_name': 'Launch', 'description': 'x', 'date': timezone.localdate().isoformat(),
            'time': '18:00', 'venue': 'Hall', 'capacity': 10, 'price': '0',
        })
        self.assertEqual(Event.objects.get().organizer, organizer)


class MyEventsPageTests(TestCase):
    url = reverse('my_events')

    def setUp(self):
        self.organizer = make_user('org', can_add_events=True)
        self.mine = make_event(event_name='Mine', organizer=self.organizer, capacity=10, price=Decimal('50'))
        self.theirs = make_event(event_name='Theirs', organizer=make_user('other', can_add_events=True))
        self.mine.book(make_user('fan'), 4)

    def test_requires_login(self):
        self.assertRedirects(self.client.get(self.url), f"{reverse('login')}?next={self.url}")

    def test_regular_user_forbidden(self):
        self.client.force_login(make_user('plain'))
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_organizer_sees_only_own_events_with_sales(self):
        self.client.force_login(self.organizer)
        response = self.client.get(self.url)
        self.assertEqual([e.event_name for e in response.context['events']], ['Mine'])
        self.assertContains(response, '<td class="num">4 / 10</td>', html=True)
        self.assertContains(response, '<td class="num">₹200.00</td>', html=True)
        self.assertContains(response, reverse('edit_event', args=[self.mine.id]))
        self.assertNotContains(response, 'Organizer</th>')

    def test_admin_sees_all_events_and_organizers(self):
        self.client.force_login(make_admin())
        response = self.client.get(self.url)
        self.assertEqual({e.event_name for e in response.context['events']}, {'Mine', 'Theirs'})
        self.assertContains(response, 'Organizer</th>')
        self.assertContains(response, 'you can manage all events')

    def test_no_edit_or_cancel_for_past_or_cancelled(self):
        past = make_event(event_name='Old', organizer=self.organizer, date=timezone.localdate() - timedelta(days=2))
        self.mine.cancel()
        self.client.force_login(self.organizer)
        response = self.client.get(self.url)
        for event in (past, self.mine):
            self.assertNotContains(response, reverse('edit_event', args=[event.id]))
            self.assertNotContains(response, reverse('cancel_event', args=[event.id]))
        self.assertContains(response, 'Cancelled')
        self.assertContains(response, 'Ended')

    def test_empty_state(self):
        self.client.force_login(make_user('newbie', can_add_events=True))
        self.assertContains(self.client.get(self.url), "You haven't created any events yet.")

    def test_query_count_does_not_grow_with_events(self):
        self.client.force_login(self.organizer)

        def count_queries():
            with CaptureQueriesContext(connection) as ctx:
                self.client.get(self.url)
            return len(ctx.captured_queries)

        baseline = count_queries()
        for i in range(5):
            make_event(organizer=self.organizer).book(make_user(f'u{i}'), 1)
        self.assertEqual(count_queries(), baseline)

    def test_nav_link_visibility(self):
        self.client.force_login(self.organizer)
        self.assertContains(self.client.get(reverse('home')), f'href="{self.url}"')
        self.client.force_login(make_user('plain'))
        self.assertNotContains(self.client.get(reverse('home')), f'href="{self.url}"')


class EditEventTests(TestCase):
    def setUp(self):
        self.organizer = make_user('org', can_add_events=True)
        self.event = make_event(event_name='Gala', organizer=self.organizer, capacity=20, price=Decimal('100'))
        self.url = reverse('edit_event', args=[self.event.id])

    def data(self, **overrides):
        data = {
            'event_name': 'Gala', 'description': 'A talk', 'date': self.event.date.isoformat(),
            'time': '18:00', 'venue': 'Hall A', 'capacity': 20, 'price': '100',
        }
        data.update(overrides)
        return data

    def test_organizer_can_edit(self):
        self.client.force_login(self.organizer)
        self.assertContains(self.client.get(self.url), 'value="Gala"')
        response = self.client.post(self.url, self.data(event_name='Grand Gala', venue='Rooftop'), follow=True)
        self.assertRedirects(response, reverse('event_detail', args=[self.event.id]))
        self.assertContains(response, 'Event &quot;Grand Gala&quot; has been updated.')
        self.event.refresh_from_db()
        self.assertEqual((self.event.event_name, self.event.venue), ('Grand Gala', 'Rooftop'))
        self.assertEqual(self.event.organizer, self.organizer)

    def test_other_organizer_forbidden(self):
        self.client.force_login(make_user('other', can_add_events=True))
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.url, self.data(event_name='Hijacked')).status_code, 403)
        self.event.refresh_from_db()
        self.assertEqual(self.event.event_name, 'Gala')

    def test_admin_can_edit(self):
        self.client.force_login(make_admin())
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_missing_event_404(self):
        self.client.force_login(self.organizer)
        self.assertEqual(self.client.get(reverse('edit_event', args=[999])).status_code, 404)

    def test_capacity_cannot_drop_below_booked_seats(self):
        self.event.book(make_user('fan'), 12)
        self.client.force_login(self.organizer)
        self.assertContains(self.client.get(self.url), 'min="12"')
        response = self.client.post(self.url, self.data(capacity=10))
        self.assertContains(response, 'Capacity cannot be less than the 12 seats already booked.')
        self.event.refresh_from_db()
        self.assertEqual(self.event.capacity, 20)
        self.client.post(self.url, self.data(capacity=12))
        self.event.refresh_from_db()
        self.assertEqual(self.event.capacity, 12)

    def test_booking_made_while_editing_is_respected(self):
        self.client.force_login(self.organizer)
        form_page = self.client.get(self.url)  # organizer opens the form with 0 booked
        self.assertContains(form_page, 'min="1"')
        self.event.book(make_user('fan'), 15)  # someone books before they submit
        response = self.client.post(self.url, self.data(capacity=10))
        self.assertContains(response, 'Capacity cannot be less than the 15 seats already booked.')

    def test_price_change_keeps_existing_booking_totals(self):
        booking = self.event.book(make_user('fan'), 2)
        self.client.force_login(self.organizer)
        self.client.post(self.url, self.data(price='300'))
        booking.refresh_from_db()
        self.assertEqual(booking.total_price, Decimal('200'))
        self.assertEqual(self.event.book(make_user('late'), 1).total_price, Decimal('300'))

    def test_cannot_edit_past_or_cancelled(self):
        self.client.force_login(self.organizer)
        self.event.cancel()
        response = self.client.get(self.url, follow=True)
        self.assertRedirects(response, reverse('my_events'))
        self.assertContains(response, 'Cancelled or past events cannot be edited.')
        past = make_event(organizer=self.organizer, date=timezone.localdate() - timedelta(days=1))
        self.assertRedirects(self.client.get(reverse('edit_event', args=[past.id])), reverse('my_events'))


class AttendeesTests(TestCase):
    def setUp(self):
        self.organizer = make_user('org', can_add_events=True)
        self.event = make_event(organizer=self.organizer, capacity=50, price=Decimal('100'))
        self.url = reverse('event_attendees', args=[self.event.id])
        self.event.book(make_user('alice'), 2)
        self.event.book(make_user('alice2'), 3)
        self.event.book(make_user('bob'), 5).cancel()

    def test_organizer_sees_bookings_and_summary(self):
        self.client.force_login(self.organizer)
        response = self.client.get(self.url)
        self.assertContains(response, 'alice@example.com')
        self.assertContains(response, 'bob@example.com')
        self.assertContains(response, '<dt>Tickets sold</dt><dd>5 / 50</dd>', html=True)
        self.assertContains(response, '<dt>Attendees</dt><dd>2</dd>', html=True)
        self.assertContains(response, '<dt>Revenue</dt><dd>₹500.00</dd>', html=True)
        self.assertContains(response, 'row-cancelled', count=1)

    def test_others_forbidden(self):
        self.client.force_login(make_user('alice3'))
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_admin_allowed(self):
        self.client.force_login(make_admin())
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_empty(self):
        self.client.force_login(self.organizer)
        empty = make_event(organizer=self.organizer)
        self.assertContains(self.client.get(reverse('event_attendees', args=[empty.id])), 'No bookings yet.')


class CancelEventTests(TestCase):
    def setUp(self):
        self.organizer = make_user('org', can_add_events=True)
        self.fan = make_user('fan')
        self.event = make_event(event_name='Gala', organizer=self.organizer, capacity=10)
        self.booking = self.event.book(self.fan, 3)
        self.url = reverse('cancel_event', args=[self.event.id])

    def test_organizer_cancels_event_and_bookings(self):
        self.client.force_login(self.organizer)
        response = self.client.post(self.url, follow=True)
        self.assertRedirects(response, reverse('my_events'))
        self.assertContains(response, 'Event &quot;Gala&quot; has been cancelled, along with 1 booking(s).')
        self.event.refresh_from_db()
        self.booking.refresh_from_db()
        self.assertTrue(self.event.is_cancelled)
        self.assertEqual(self.booking.status, Booking.Status.CANCELLED)

    def test_get_not_allowed(self):
        self.client.force_login(self.organizer)
        self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_other_user_forbidden(self):
        self.client.force_login(make_user('other', can_add_events=True))
        self.assertEqual(self.client.post(self.url).status_code, 403)
        self.event.refresh_from_db()
        self.assertFalse(self.event.is_cancelled)

    def test_already_cancelled_shows_error(self):
        self.client.force_login(self.organizer)
        self.client.post(self.url)
        response = self.client.post(self.url, follow=True)
        self.assertContains(response, 'This event can no longer be cancelled.')

    def test_cancelled_event_everywhere(self):
        self.client.force_login(self.organizer)
        self.client.post(self.url)

        self.client.force_login(self.fan)
        detail = self.client.get(reverse('event_detail', args=[self.event.id]))
        self.assertContains(detail, 'This event has been cancelled by the organizer.')
        self.assertContains(detail, 'Event Cancelled')
        self.assertNotContains(detail, 'Book Now')

        book = self.client.get(reverse('book_event', args=[self.event.id]))
        self.assertContains(book, 'This event has been cancelled.')
        self.assertNotContains(book, 'name="number_of_tickets"')

        listing = self.client.get(reverse('event_list'))
        self.assertContains(listing, '<span class="badge badge-soldout">Cancelled</span>', html=True)
        self.assertEqual(list(self.client.get(reverse('event_list'), {'available': 'on'}).context['events']), [])

        bookings = self.client.get(reverse('my_bookings'))
        self.assertContains(bookings, 'This event was cancelled by the organizer.')
        self.assertNotContains(bookings, 'Cancel Booking')


class OrganizerControlsOnDetailTests(TestCase):
    def test_manage_buttons_only_for_managers(self):
        organizer = make_user('org', can_add_events=True)
        event = make_event(organizer=organizer)
        url = reverse('event_detail', args=[event.id])
        edit = reverse('edit_event', args=[event.id])

        self.client.force_login(organizer)
        self.assertContains(self.client.get(url), edit)
        self.client.force_login(make_user('fan'))
        self.assertNotContains(self.client.get(url), edit)
        self.client.logout()
        self.assertNotContains(self.client.get(url), edit)
