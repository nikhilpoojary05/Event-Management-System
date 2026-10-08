from datetime import timedelta

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from ..forms import BookingForm, EventForm


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

    def test_requires_all_fields(self):
        form = EventForm({})
        self.assertFalse(form.is_valid())
        self.assertEqual(
            set(form.errors),
            {'event_name', 'description', 'date', 'time', 'venue', 'capacity', 'price'},
        )


class EventFormWidgetTests(SimpleTestCase):
    def test_uses_native_date_and_time_inputs(self):
        html = str(EventForm())
        self.assertIn('type="date"', html)
        self.assertIn(f'min="{timezone.localdate().isoformat()}"', html)
        self.assertIn('type="time"', html)

    def test_capacity_input_minimum_is_one(self):
        self.assertIn('min="1"', str(EventForm()['capacity']))


class BookingFormTests(SimpleTestCase):
    def test_accepts_positive_tickets(self):
        self.assertTrue(BookingForm({'number_of_tickets': 2}).is_valid())

    def test_rejects_zero_or_negative_tickets(self):
        for tickets in (0, -5):
            self.assertFalse(BookingForm({'number_of_tickets': tickets}).is_valid())
