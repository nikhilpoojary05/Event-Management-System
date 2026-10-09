from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .. import login_throttle
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
        response = self.client.post(self.url, self.data(), follow=True)
        self.assertRedirects(response, reverse('event_list'))
        self.assertContains(response, 'Welcome, newuser! Your account has been created.')
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
        response = self.client.post(reverse('logout'), follow=True)
        self.assertRedirects(response, reverse('home'))
        self.assertContains(response, 'You have been logged out.')
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_get_does_not_log_out(self):
        # A link or <img> on another site can trigger a GET, so GET must not log the user out.
        self.client.force_login(make_user())
        self.assertEqual(self.client.get(reverse('logout')).status_code, 405)
        self.assertIn('_auth_user_id', self.client.session)

    def test_logout_requires_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(make_user())
        self.assertEqual(client.post(reverse('logout')).status_code, 403)
        self.assertIn('_auth_user_id', client.session)

    def test_nav_logout_is_a_csrf_protected_form(self):
        self.client.force_login(make_user())
        response = self.client.get(reverse('home'))
        self.assertContains(response, f'<form method="post" action="{reverse("logout")}" class="nav-form">')
        self.assertContains(response, 'name="csrfmiddlewaretoken"')
        self.assertNotContains(response, f'href="{reverse("logout")}"')


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
        response = self.client.post(self.url, self.event_data(), follow=True)
        event = Event.objects.get()
        self.assertRedirects(response, reverse('event_detail', args=[event.id]))
        self.assertEqual((event.event_name, event.capacity), ('Launch Party', 40))
        self.assertContains(response, 'Event &quot;Launch Party&quot; has been created.')

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


class TestRunnerTests(TestCase):
    def test_suite_uses_fast_hasher_but_production_settings_do_not(self):
        from django.conf import settings

        from event_management_system import settings as project_settings
        self.assertEqual(settings.PASSWORD_HASHERS, ['django.contrib.auth.hashers.MD5PasswordHasher'])
        self.assertFalse(hasattr(project_settings, 'PASSWORD_HASHERS'))


REAL_CACHE = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'lockout-tests'}}


@override_settings(CACHES=REAL_CACHE)  # the test runner uses a no-op cache elsewhere
class LoginLockoutTests(TestCase):
    url = reverse('login')

    def setUp(self):
        cache.clear()
        make_user('alice')

    def fail(self, username='alice', ip='10.0.0.1'):
        return self.client.post(self.url, {'username': username, 'password': 'wrong'}, REMOTE_ADDR=ip)

    def test_invalid_login_message(self):
        self.assertContains(self.fail(), 'Invalid username or password.')

    def test_locked_out_after_five_failures_even_with_correct_password(self):
        for _ in range(login_throttle.MAX_FAILURES):
            self.assertEqual(self.fail().status_code, 200)
        response = self.client.post(self.url, {'username': 'alice', 'password': PASSWORD}, REMOTE_ADDR='10.0.0.1')
        self.assertEqual(response.status_code, 429)
        self.assertContains(response, 'Too many failed login attempts', status_code=429)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_lockout_applies_to_username_from_another_ip(self):
        for i in range(login_throttle.MAX_FAILURES):
            self.fail(ip=f'10.0.0.{i}')
        response = self.client.post(self.url, {'username': 'alice', 'password': PASSWORD}, REMOTE_ADDR='10.9.9.9')
        self.assertEqual(response.status_code, 429)

    def test_lockout_applies_to_ip_trying_many_usernames(self):
        for i in range(login_throttle.MAX_FAILURES):
            self.fail(username=f'guess{i}')
        response = self.client.post(self.url, {'username': 'alice', 'password': PASSWORD}, REMOTE_ADDR='10.0.0.1')
        self.assertEqual(response.status_code, 429)

    def test_success_resets_counter(self):
        for _ in range(login_throttle.MAX_FAILURES - 1):
            self.fail()
        self.client.post(self.url, {'username': 'alice', 'password': PASSWORD}, REMOTE_ADDR='10.0.0.1')
        self.client.logout()
        for _ in range(login_throttle.MAX_FAILURES - 1):
            self.fail()
        response = self.client.post(self.url, {'username': 'alice', 'password': PASSWORD}, REMOTE_ADDR='10.0.0.1')
        self.assertEqual(response.status_code, 302)

    def test_lockout_expires(self):
        for _ in range(login_throttle.MAX_FAILURES):
            self.fail()
        cache.clear()  # what expiry of the lockout window does
        response = self.client.post(self.url, {'username': 'alice', 'password': PASSWORD}, REMOTE_ADDR='10.0.0.1')
        self.assertEqual(response.status_code, 302)

    def test_logged_in_user_is_redirected_away_from_login(self):
        self.client.force_login(User.objects.get(username='alice'))
        self.assertRedirects(self.client.get(self.url), reverse('event_list'))

    def test_inactive_user_cannot_log_in(self):
        User.objects.filter(username='alice').update(is_active=False)
        response = self.client.post(self.url, {'username': 'alice', 'password': PASSWORD})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)
