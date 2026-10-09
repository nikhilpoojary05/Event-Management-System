from datetime import time, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from ..views import EVENTS_PER_PAGE
from .factories import make_event, make_user


class EventListTests(TestCase):
    url = reverse('event_list')

    def names(self, response):
        return [e.event_name for e in response.context['events']]

    def test_upcoming_only_sorted_soonest_first(self):
        today = timezone.localdate()
        make_event(event_name='Later', date=today + timedelta(days=10))
        make_event(event_name='Today Evening', date=today, time=time(20, 0))
        make_event(event_name='Today Morning', date=today, time=time(9, 0))
        make_event(event_name='Yesterday', date=today - timedelta(days=1))
        response = self.client.get(self.url)
        self.assertEqual(self.names(response), ['Today Morning', 'Today Evening', 'Later'])
        self.assertNotContains(response, 'Yesterday')

    def test_past_tab_most_recent_first(self):
        today = timezone.localdate()
        make_event(event_name='Upcoming')
        make_event(event_name='Last Month', date=today - timedelta(days=30))
        make_event(event_name='Yesterday', date=today - timedelta(days=1))
        response = self.client.get(self.url, {'when': 'past'})
        self.assertEqual(self.names(response), ['Yesterday', 'Last Month'])
        self.assertContains(response, 'Past Events')
        self.assertContains(response, '?when=past" aria-current="page"')

    def test_seats_left_ignores_cancelled_bookings(self):
        event = make_event(event_name='Tech Talk', capacity=10)
        event.book(make_user('alice'), 3)
        event.book(make_user('bob'), 2).cancel()
        response = self.client.get(self.url)
        self.assertEqual(response.context['events'][0].seats_left, 7)
        self.assertContains(response, '7 of 10')

    def test_badges(self):
        make_event(event_name='Full', capacity=2).book(make_user('alice'), 2)
        make_event(event_name='Almost', capacity=10).book(make_user('bob'), 7)
        make_event(event_name='Roomy', capacity=100)
        response = self.client.get(self.url)
        self.assertContains(response, 'Sold out', count=1)
        self.assertContains(response, 'Only 3 left', count=1)

    def test_paginates(self):
        for i in range(EVENTS_PER_PAGE + 3):
            make_event(event_name=f'Event {i:02d}', date=timezone.localdate() + timedelta(days=i + 1))
        first = self.client.get(self.url)
        self.assertEqual(len(first.context['events']), EVENTS_PER_PAGE)
        self.assertContains(first, 'Page 1 of 2')
        self.assertContains(first, 'href="?page=2"')
        second = self.client.get(self.url, {'page': 2})
        self.assertEqual(self.names(second), ['Event 10', 'Event 11', 'Event 12'])
        self.assertContains(second, 'href="?page=1"')

    def test_invalid_page_falls_back(self):
        make_event()
        for page in ('abc', '999'):
            self.assertEqual(self.client.get(self.url, {'page': page}).status_code, 200)

    def test_past_pagination_keeps_tab(self):
        for i in range(EVENTS_PER_PAGE + 1):
            make_event(date=timezone.localdate() - timedelta(days=i + 1))
        response = self.client.get(self.url, {'when': 'past'})
        self.assertContains(response, 'href="?when=past&amp;page=2"')

    def test_query_count_does_not_grow_with_events(self):
        for i in range(EVENTS_PER_PAGE):
            make_event().book(make_user(f'user{i}'), 1)
        with self.assertNumQueries(2):  # count + page of events with seat counts
            self.client.get(self.url)

    def test_empty_states(self):
        self.assertContains(self.client.get(self.url), 'No upcoming events.')
        self.assertContains(self.client.get(self.url, {'when': 'past'}), 'No past events.')


class EventDetailTests(TestCase):
    def setUp(self):
        self.event = make_event(capacity=10)
        self.url = reverse('event_detail', args=[self.event.id])

    def test_missing_event_404(self):
        self.assertEqual(self.client.get(reverse('event_detail', args=[999])).status_code, 404)

    def test_shows_remaining_seats(self):
        self.event.book(make_user('bob'), 4)
        response = self.client.get(self.url)
        self.assertEqual(response.context['remaining_seats'], 6)

    def test_anonymous_sees_login_to_book(self):
        response = self.client.get(self.url)
        book_url = reverse('book_event', args=[self.event.id])
        self.assertContains(response, f"{reverse('login')}?next={book_url}")

    def test_logged_in_sees_book_now(self):
        self.client.force_login(make_user())
        self.assertContains(self.client.get(self.url), 'Book Now')

    def test_full_event_shows_booking_closed(self):
        self.event.book(make_user('bob'), 10)
        self.client.force_login(make_user())
        response = self.client.get(self.url)
        self.assertContains(response, 'Join Waitlist')
        self.assertNotContains(response, 'Book Now')


class MyBookingsTests(TestCase):
    url = reverse('my_bookings')

    def test_requires_login(self):
        response = self.client.get(self.url)
        self.assertRedirects(response, f"{reverse('login')}?next={self.url}")

    def test_shows_only_own_bookings(self):
        alice, bob = make_user('alice'), make_user('bob')
        make_event(event_name='Alice Event').book(alice, 2)
        make_event(event_name='Bob Event').book(bob, 1)
        self.client.force_login(alice)
        response = self.client.get(self.url)
        self.assertContains(response, 'Alice Event')
        self.assertNotContains(response, 'Bob Event')

    def test_empty_state(self):
        self.client.force_login(make_user())
        self.assertContains(self.client.get(self.url), 'You have no bookings yet.')


class LayoutTests(TestCase):
    def setUp(self):
        self.event = make_event()

    def public_urls(self):
        return [reverse('home'), reverse('event_list'), reverse('event_detail', args=[self.event.id]),
                reverse('login'), reverse('register')]

    def private_urls(self):
        return [reverse('my_bookings'), reverse('book_event', args=[self.event.id]), reverse('add_event')]

    def test_every_page_uses_base_layout(self):
        self.client.force_login(make_user(can_add_events=True))
        logged_in_pages = [u for u in self.public_urls() if u != reverse('login')]  # login redirects when logged in
        for url in logged_in_pages + self.private_urls():
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertTemplateUsed(response, 'events/base.html')
                self.assertContains(response, '<html lang="en">')
                self.assertContains(response, 'name="viewport"')
                self.assertContains(response, '<nav class="nav-links" aria-label="Main">', count=1)

    def test_nav_for_anonymous_user(self):
        response = self.client.get(reverse('home'))
        self.assertContains(response, f'href="{reverse("login")}"')
        self.assertContains(response, f'href="{reverse("register")}"')
        self.assertNotContains(response, 'My Bookings')
        self.assertNotContains(response, 'Logout')

    def test_nav_for_logged_in_user_is_same_on_every_page(self):
        self.client.force_login(make_user())
        logged_in_pages = [u for u in self.public_urls() if u != reverse('login')]
        for url in logged_in_pages + self.private_urls()[:2]:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertContains(response, f'href="{reverse("my_bookings")}"')
                self.assertContains(response, f'action="{reverse("logout")}"')
                self.assertNotContains(response, f'href="{reverse("add_event")}"')

    def test_current_page_marked_in_nav(self):
        response = self.client.get(reverse('event_list'))
        self.assertContains(response, f'href="{reverse("event_list")}" aria-current="page">Events<')
        self.assertContains(response, f'href="{reverse("home")}">Home<')

        response = self.client.get(reverse('home'))
        self.assertContains(response, f'href="{reverse("home")}" aria-current="page">Home<')
        self.assertContains(response, 'aria-current="page"', count=1)

    def test_page_titles(self):
        self.assertContains(self.client.get(reverse('home')), '<title>Home | Event Management</title>')
        detail = self.client.get(reverse('event_detail', args=[self.event.id]))
        self.assertContains(detail, '<title>Tech Talk | Event Management</title>')
