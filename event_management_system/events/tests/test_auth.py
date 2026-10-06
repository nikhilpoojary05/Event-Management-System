from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from ..models import Event
from .factories import PASSWORD, make_user


class RegisterTests(TestCase):
    url = reverse('register')

    def data(self, **overrides):
        data = {
            'username': 'newuser',
            'email': 'new@example.com',
            'password1': 'a-Strong-pass-42',
            'password2': 'a-Strong-pass-42',
        }
        data.update(overrides)
        return data

    def test_register_creates_user_and_logs_in(self):
        response = self.client.post(self.url, self.data())
        self.assertRedirects(response, reverse('event_list'))
        user = User.objects.get(username='newuser')
        self.assertEqual(user.email, 'new@example.com')
        self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)

    def test_mismatched_passwords_rejected(self):
        response = self.client.post(self.url, self.data(password2='something-else-42'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('password2', response.context['form'].errors)
        self.assertFalse(User.objects.filter(username='newuser').exists())

    def test_duplicate_username_rejected(self):
        make_user('newuser')
        response = self.client.post(self.url, self.data())
        self.assertIn('username', response.context['form'].errors)

    def test_email_required(self):
        response = self.client.post(self.url, self.data(email=''))
        self.assertIn('email', response.context['form'].errors)


class LoginTests(TestCase):
    def setUp(self):
        make_user('alice')
        self.creds = {'username': 'alice', 'password': PASSWORD}

    def test_redirects_to_next(self):
        target = reverse('my_bookings')
        response = self.client.post(reverse('login'), {**self.creds, 'next': target})
        self.assertRedirects(response, target)

    def test_defaults_to_event_list(self):
        response = self.client.post(reverse('login'), self.creds)
        self.assertRedirects(response, reverse('event_list'))

    def test_ignores_external_next(self):
        response = self.client.post(reverse('login'), {**self.creds, 'next': 'https://evil.example.com/'})
        self.assertRedirects(response, reverse('event_list'))

    def test_next_carried_through_login_form(self):
        target = reverse('my_bookings')
        response = self.client.get(reverse('login'), {'next': target})
        self.assertContains(response, f'name="next" value="{target}"')

    def test_failed_login_keeps_next(self):
        target = reverse('my_bookings')
        response = self.client.post(reverse('login'), {'username': 'alice', 'password': 'wrong', 'next': target})
        self.assertContains(response, 'Invalid username or password')
        self.assertContains(response, f'name="next" value="{target}"')
        self.assertNotIn('_auth_user_id', self.client.session)


class LogoutTests(TestCase):
    def test_logout_ends_session(self):
        self.client.force_login(make_user())
        response = self.client.get(reverse('logout'))
        self.assertRedirects(response, reverse('home'))
        self.assertNotIn('_auth_user_id', self.client.session)


class AddEventPermissionTests(TestCase):
    url = reverse('add_event')

    def event_data(self):
        return {
            'event_name': 'Launch Party',
            'description': 'Celebration',
            'date': timezone.localdate().isoformat(),
            'time': '19:30',
            'venue': 'Rooftop',
            'capacity': 40,
            'price': '150.00',
        }

    def test_anonymous_redirected_to_login(self):
        response = self.client.get(self.url)
        self.assertRedirects(response, f"{reverse('login')}?next={self.url}")

    def test_regular_user_forbidden(self):
        self.client.force_login(make_user())
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.url, self.event_data()).status_code, 403)
        self.assertFalse(Event.objects.exists())
        self.assertNotContains(self.client.get(reverse('event_list')), 'Add Event')

    def test_user_with_permission_sees_form_and_link(self):
        self.client.force_login(make_user(can_add_events=True))
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertContains(self.client.get(reverse('event_list')), 'Add Event')

    def test_user_with_permission_creates_event(self):
        self.client.force_login(make_user(can_add_events=True))
        response = self.client.post(self.url, self.event_data())
        self.assertRedirects(response, reverse('event_list'))
        event = Event.objects.get()
        self.assertEqual((event.event_name, event.capacity), ('Launch Party', 40))

    def test_invalid_event_redisplays_form(self):
        self.client.force_login(make_user(can_add_events=True))
        response = self.client.post(self.url, {**self.event_data(), 'capacity': 0})
        self.assertEqual(response.status_code, 200)
        self.assertIn('capacity', response.context['form'].errors)
        self.assertFalse(Event.objects.exists())

    def test_superuser_can_add(self):
        admin = User.objects.create_superuser('root', 'root@example.com', PASSWORD)
        self.client.force_login(admin)
        self.assertEqual(self.client.get(self.url).status_code, 200)
