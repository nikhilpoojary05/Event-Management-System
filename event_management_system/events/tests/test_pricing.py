from decimal import Decimal

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from ..models import Booking
from ..templatetags.events_extras import price
from .factories import PASSWORD, make_event, make_user


class PriceFilterTests(SimpleTestCase):
    def test_formats(self):
        self.assertEqual(price(Decimal('0')), 'Free')
        self.assertEqual(price(Decimal('0.00')), 'Free')
        self.assertEqual(price(Decimal('50')), '₹50.00')
        self.assertEqual(price(Decimal('1500.5')), '₹1,500.50')
        self.assertEqual(price(None), '')


class BookingPriceTests(TestCase):
    def test_booking_snapshots_unit_price_and_totals(self):
        event = make_event(price=Decimal('120.50'))
        booking = event.book(make_user(), 3)
        self.assertEqual(booking.unit_price, Decimal('120.50'))
        self.assertEqual(booking.total_price, Decimal('361.50'))

    def test_later_price_change_does_not_alter_existing_booking(self):
        event = make_event(price=Decimal('100'))
        booking = event.book(make_user(), 2)
        event.price = Decimal('250')
        event.save()
        booking.refresh_from_db()
        self.assertEqual(booking.total_price, Decimal('200'))

    def test_free_event_total_is_zero(self):
        self.assertEqual(make_event(price=0).book(make_user(), 4).total_price, 0)


class BookingSummaryPageTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.event = make_event(event_name='Jazz Night', venue='Blue Room', capacity=10, price=Decimal('150'))
        self.url = reverse('book_event', args=[self.event.id])
        self.client.force_login(self.user)

    def test_shows_summary_and_default_total(self):
        self.event.book(make_user('bob'), 4)
        response = self.client.get(self.url)
        self.assertContains(response, 'Blue Room')
        self.assertContains(response, '<dt>Price per ticket</dt><dd>₹150.00</dd>', html=True)
        self.assertContains(response, '<dt>Seats left</dt><dd>6</dd>', html=True)
        self.assertContains(response, 'data-unit-price="150.00"')
        self.assertEqual(response.context['total'], Decimal('150'))

    def test_ticket_input_capped_at_seats_left(self):
        self.event.book(make_user('bob'), 7)
        response = self.client.get(self.url)
        self.assertContains(response, 'max="3"')
        self.assertContains(response, 'min="1"')

    def test_invalid_post_keeps_total_for_entered_tickets(self):
        self.event.book(make_user('bob'), 8)
        response = self.client.post(self.url, {'number_of_tickets': 3})
        self.assertContains(response, 'Not enough seats available!')
        self.assertEqual(response.context['total'], Decimal('450'))
        self.assertFalse(Booking.objects.filter(user=self.user).exists())

    def test_unparseable_ticket_count_falls_back_to_one(self):
        response = self.client.post(self.url, {'number_of_tickets': 'abc'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total'], Decimal('150'))

    def test_success_message_includes_total(self):
        response = self.client.post(self.url, {'number_of_tickets': 3}, follow=True)
        self.assertContains(response, 'Booked 3 ticket(s) for Jazz Night. Total: ₹450.00.')

    def test_free_event_says_free(self):
        free = make_event(event_name='Open Day', price=0)
        url = reverse('book_event', args=[free.id])
        self.assertContains(self.client.get(url), '<dt>Price per ticket</dt><dd>Free</dd>', html=True)
        response = self.client.post(url, {'number_of_tickets': 2}, follow=True)
        self.assertContains(response, 'Total: Free.')

    def test_closed_event_has_no_summary(self):
        self.event.book(make_user('bob'), 10)
        response = self.client.get(self.url)
        self.assertNotContains(response, 'booking-total')


class PriceDisplayTests(TestCase):
    def test_list_and_detail_show_free_and_formatted_prices(self):
        free = make_event(event_name='Open Day', price=0)
        paid = make_event(event_name='Gala', price=Decimal('1200'))
        response = self.client.get(reverse('event_list'))
        self.assertContains(response, '<strong>Price:</strong> Free', html=True)
        self.assertContains(response, '<strong>Price:</strong> ₹1,200.00', html=True)
        self.assertNotContains(response, '₹0.00')
        self.assertContains(self.client.get(reverse('event_detail', args=[free.id])), 'Free')
        self.assertContains(self.client.get(reverse('event_detail', args=[paid.id])), '₹1,200.00')

    def test_my_bookings_shows_breakdown_and_total(self):
        user = make_user()
        make_event(event_name='Gala', price=Decimal('1200')).book(user, 2)
        self.client.force_login(user)
        response = self.client.get(reverse('my_bookings'))
        self.assertContains(response, '2 &times; ₹1,200.00')
        self.assertContains(response, '<strong>Total:</strong> ₹2,400.00', html=True)

    def test_admin_booking_list_shows_total(self):
        make_event(price=Decimal('75')).book(make_user(), 4)
        self.client.force_login(User.objects.create_superuser('root', 'root@example.com', PASSWORD))
        response = self.client.get(reverse('admin:events_booking_changelist'))
        self.assertContains(response, '<td class="field-total">300.00</td>', html=True)
