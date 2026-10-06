from django.test import TestCase
from django.urls import reverse

from .factories import make_event, make_user


class EventListTests(TestCase):
    def test_lists_events(self):
        make_event(event_name='Tech Talk')
        make_event(event_name='Jazz Night')
        response = self.client.get(reverse('event_list'))
        self.assertContains(response, 'Tech Talk')
        self.assertContains(response, 'Jazz Night')

    def test_empty_state(self):
        self.assertContains(self.client.get(reverse('event_list')), 'No events available.')


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
        self.assertContains(response, 'Booking Closed')
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
        for url in self.public_urls() + self.private_urls():
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
        for url in self.public_urls() + self.private_urls()[:2]:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertContains(response, f'href="{reverse("my_bookings")}"')
                self.assertContains(response, f'href="{reverse("logout")}"')
                self.assertNotContains(response, f'href="{reverse("add_event")}"')

    def test_current_page_marked_in_nav(self):
        response = self.client.get(reverse('event_list'))
        self.assertContains(response, f'href="{reverse("event_list")}" aria-current="page"')
        self.assertContains(response, 'aria-current="page"', count=1)

    def test_page_titles(self):
        self.assertContains(self.client.get(reverse('home')), '<title>Home | Event Management</title>')
        detail = self.client.get(reverse('event_detail', args=[self.event.id]))
        self.assertContains(detail, '<title>Tech Talk | Event Management</title>')
