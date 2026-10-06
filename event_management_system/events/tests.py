from datetime import time, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .forms import BookingForm, EventForm
from .models import Booking, Event


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


class EventFormValidationTests(TestCase):
    def form_data(self, **overrides):
        data = {
            'event_name': 'Tech Talk',
            'description': 'A talk',
            'date': (timezone.localdate() + timedelta(days=1)).isoformat(),
            'time': '18:00',
            'venue': 'Hall A',
            'capacity': 50,
            'price': '0',
        }
        data.update(overrides)
        return data

    def test_valid_event(self):
        self.assertTrue(EventForm(self.form_data()).is_valid())

    def test_rejects_past_date(self):
        past = (timezone.localdate() - timedelta(days=1)).isoformat()
        form = EventForm(self.form_data(date=past))
        self.assertFalse(form.is_valid())
        self.assertIn('date', form.errors)

    def test_allows_today(self):
        self.assertTrue(EventForm(self.form_data(date=timezone.localdate().isoformat())).is_valid())

    def test_rejects_zero_or_negative_capacity(self):
        for capacity in (0, -10):
            form = EventForm(self.form_data(capacity=capacity))
            self.assertFalse(form.is_valid())
            self.assertIn('capacity', form.errors)

    def test_rejects_negative_price(self):
        form = EventForm(self.form_data(price='-50'))
        self.assertFalse(form.is_valid())
        self.assertIn('price', form.errors)


class BookingValidationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('alice', password='pw-for-tests-123')
        self.event = make_event(capacity=10)

    def test_booking_form_rejects_zero_or_negative_tickets(self):
        for tickets in (0, -5):
            self.assertFalse(BookingForm({'number_of_tickets': tickets}).is_valid())

    def test_negative_booking_cannot_free_seats(self):
        self.client.force_login(self.user)
        Booking.objects.create(user=self.user, event=self.event, number_of_tickets=10)

        self.client.post(reverse('book_event', args=[self.event.id]), {'number_of_tickets': -5})
        response = self.client.post(reverse('book_event', args=[self.event.id]), {'number_of_tickets': 3})

        self.assertEqual(Booking.objects.filter(event=self.event).count(), 1)
        self.assertContains(response, 'This event is full')
