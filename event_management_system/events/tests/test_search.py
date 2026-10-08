from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from ..models import Event
from ..views import EVENTS_PER_PAGE
from .factories import make_event, make_user


def days(n):
    return timezone.localdate() + timedelta(days=n)


class EventSearchQuerySetTests(TestCase):
    def setUp(self):
        make_event(event_name='Jazz Night', venue='Blue Room', description='Live music')
        make_event(event_name='Python Workshop', venue='Lab 3', description='Hands-on coding')
        make_event(event_name='Tech Talk', venue='Hall A', description='All about Python and AI')

    def names(self, qs):
        return sorted(qs.values_list('event_name', flat=True))

    def test_matches_name_venue_or_description_case_insensitively(self):
        self.assertEqual(self.names(Event.objects.search('jazz')), ['Jazz Night'])
        self.assertEqual(self.names(Event.objects.search('LAB')), ['Python Workshop'])
        self.assertEqual(self.names(Event.objects.search('python')), ['Python Workshop', 'Tech Talk'])

    def test_every_word_must_match(self):
        self.assertEqual(self.names(Event.objects.search('python hall')), ['Tech Talk'])
        self.assertEqual(self.names(Event.objects.search('python jazz')), [])

    def test_blank_search_returns_everything(self):
        self.assertEqual(Event.objects.search('   ').count(), 3)


class EventListFilterTests(TestCase):
    url = reverse('event_list')

    def names(self, response):
        return [e.event_name for e in response.context['events']]

    def test_search_by_text(self):
        make_event(event_name='Jazz Night', date=days(1))
        make_event(event_name='Tech Talk', date=days(2))
        response = self.client.get(self.url, {'q': 'jazz'})
        self.assertEqual(self.names(response), ['Jazz Night'])
        self.assertContains(response, '1 event found')
        self.assertContains(response, 'value="jazz"')

    def test_date_range(self):
        for n in (1, 5, 10, 20):
            make_event(event_name=f'Day {n}', date=days(n))
        response = self.client.get(self.url, {'date_from': days(5).isoformat(), 'date_to': days(10).isoformat()})
        self.assertEqual(self.names(response), ['Day 5', 'Day 10'])
        self.assertContains(response, '2 events found')

    def test_free_only(self):
        make_event(event_name='Paid', price=100)
        make_event(event_name='Open Day', price=0)
        self.assertEqual(self.names(self.client.get(self.url, {'free': 'on'})), ['Open Day'])

    def test_has_seats_left(self):
        make_event(event_name='Full', capacity=2, date=days(1)).book(make_user('a'), 2)
        cancelled = make_event(event_name='Freed Up', capacity=2, date=days(2))
        cancelled.book(make_user('b'), 2).cancel()
        make_event(event_name='Roomy', capacity=50, date=days(3))
        self.assertEqual(self.names(self.client.get(self.url, {'available': 'on'})), ['Freed Up', 'Roomy'])

    def test_filters_combine(self):
        make_event(event_name='Free Jazz', price=0, date=days(1))
        make_event(event_name='Paid Jazz', price=200, date=days(2))
        make_event(event_name='Free Talk', price=0, date=days(3))
        response = self.client.get(self.url, {'q': 'jazz', 'free': 'on'})
        self.assertEqual(self.names(response), ['Free Jazz'])

    def test_filters_apply_to_past_tab(self):
        make_event(event_name='Old Jazz', date=days(-3))
        make_event(event_name='Old Talk', date=days(-2))
        make_event(event_name='New Jazz', date=days(2))
        response = self.client.get(self.url, {'when': 'past', 'q': 'jazz'})
        self.assertEqual(self.names(response), ['Old Jazz'])
        self.assertContains(response, '<input type="hidden" name="when" value="past">', html=True)

    def test_no_matches_message(self):
        make_event(event_name='Jazz Night')
        response = self.client.get(self.url, {'q': 'opera'})
        self.assertContains(response, 'No events match your filters.')
        self.assertContains(response, '0 events found')

    def test_invalid_dates_show_errors_and_ignore_filters(self):
        make_event(event_name='Jazz Night', date=days(1))
        response = self.client.get(self.url, {'date_from': 'not-a-date', 'q': 'opera'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Enter a valid date.')
        self.assertEqual(self.names(response), ['Jazz Night'])

    def test_date_range_must_be_in_order(self):
        response = self.client.get(self.url, {'date_from': days(10).isoformat(), 'date_to': days(1).isoformat()})
        self.assertContains(response, "&#x27;To&#x27; date must be on or after the &#x27;From&#x27; date.")

    def test_unfiltered_list_has_no_count_or_clear_link(self):
        make_event()
        response = self.client.get(self.url)
        self.assertNotContains(response, 'found')
        self.assertNotContains(response, 'Clear filters')

    def test_clear_filters_link_keeps_tab(self):
        response = self.client.get(self.url, {'when': 'past', 'q': 'x'})
        self.assertContains(response, 'href="?when=past" class="btn btn-secondary">Clear filters')
        response = self.client.get(self.url, {'q': 'x'})
        self.assertContains(response, f'href="{self.url}" class="btn btn-secondary">Clear filters')

    def test_tabs_keep_filters_and_reset_page(self):
        response = self.client.get(self.url, {'q': 'jazz', 'free': 'on', 'page': '2'})
        self.assertContains(response, 'href="?q=jazz&amp;free=on&amp;when=past"')
        response = self.client.get(self.url, {'when': 'past', 'q': 'jazz'})
        self.assertContains(response, 'href="?q=jazz">Upcoming</a>')

    def test_pagination_keeps_filters(self):
        for i in range(EVENTS_PER_PAGE + 2):
            make_event(event_name=f'Jazz {i:02d}', date=days(i + 1))
        make_event(event_name='Unrelated')
        first = self.client.get(self.url, {'q': 'jazz'})
        self.assertContains(first, f'{EVENTS_PER_PAGE + 2} events found')
        self.assertContains(first, 'href="?q=jazz&amp;page=2"')
        second = self.client.get(self.url, {'q': 'jazz', 'page': 2})
        self.assertEqual(self.names(second), ['Jazz 10', 'Jazz 11'])

    def test_filtering_does_not_add_queries(self):
        for i in range(5):
            make_event(event_name=f'Jazz {i}').book(make_user(f'u{i}'), 1)
        with self.assertNumQueries(2):
            self.client.get(self.url, {'q': 'jazz', 'available': 'on', 'date_from': days(0).isoformat()})
