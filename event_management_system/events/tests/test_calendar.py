from datetime import date, time, timedelta

from django.core import mail
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .. import calendar
from .factories import make_event, make_user


def unfold(ics):
    return ics.replace('\r\n ', '')


@override_settings(SITE_URL='https://events.example.com', TIME_ZONE='Asia/Kolkata')
class BuildIcsTests(TestCase):
    def setUp(self):
        self.event = make_event(
            event_name='AI, Data; & Future', venue='Hall A, Block 2', description='Line one\nLine two',
            date=date(2030, 3, 15), time=time(18, 30),
        )

    def test_structure_and_utc_times(self):
        ics = calendar.build_ics(self.event)
        self.assertTrue(ics.startswith('BEGIN:VCALENDAR\r\nVERSION:2.0\r\n'))
        self.assertTrue(ics.endswith('END:VEVENT\r\nEND:VCALENDAR\r\n'))
        self.assertIn('\r\nDTSTART:20300315T130000Z\r\n', ics)  # 18:30 IST = 13:00 UTC
        self.assertIn('\r\nDTEND:20300315T150000Z\r\n', ics)  # default 2-hour duration
        self.assertIn(f'\r\nUID:event-{self.event.pk}@events.example.com\r\n', ics)
        self.assertIn(f'URL:https://events.example.com/event/{self.event.pk}/', unfold(ics))
        self.assertIn('STATUS:CONFIRMED', ics)

    def test_text_is_escaped(self):
        ics = unfold(calendar.build_ics(self.event))
        self.assertIn('SUMMARY:AI\\, Data\\; & Future\r\n', ics)
        self.assertIn('LOCATION:Hall A\\, Block 2\r\n', ics)
        self.assertIn('DESCRIPTION:Line one\\nLine two\r\n', ics)

    def test_cancelled_status(self):
        self.event.is_cancelled = True
        self.assertIn('STATUS:CANCELLED', calendar.build_ics(self.event))

    def test_filename(self):
        self.assertEqual(calendar.filename(self.event), 'ai--data----future.ics')


class FoldingTests(SimpleTestCase):
    def test_long_lines_are_folded_to_75_octets(self):
        line = 'DESCRIPTION:' + 'நிகழ்வு ' * 30  # multi-byte characters
        folded = calendar._fold(line)
        for part in folded.split('\r\n'):
            self.assertLessEqual(len(part.encode('utf-8')), 75)
        self.assertEqual(folded.replace('\r\n ', ''), line)

    def test_short_lines_untouched(self):
        self.assertEqual(calendar._fold('SUMMARY:Hi'), 'SUMMARY:Hi')


class CalendarDownloadTests(TestCase):
    def test_download(self):
        event = make_event(event_name='Jazz Night')
        response = self.client.get(reverse('event_calendar', args=[event.id]))
        self.assertEqual(response['Content-Type'], 'text/calendar; charset=utf-8')
        self.assertEqual(response['Content-Disposition'], 'attachment; filename="jazz-night.ics"')
        self.assertIn('SUMMARY:Jazz Night', response.content.decode())

    def test_missing_event_404(self):
        self.assertEqual(self.client.get(reverse('event_calendar', args=[999])).status_code, 404)

    def test_links_shown_for_upcoming_events_only(self):
        upcoming = make_event()
        past = make_event(date=timezone.localdate() - timedelta(days=1))
        self.assertContains(self.client.get(reverse('event_detail', args=[upcoming.id])), 'Add to calendar')
        self.assertNotContains(self.client.get(reverse('event_detail', args=[past.id])), 'Add to calendar')

        user = make_user()
        booking = upcoming.book(user, 1)
        self.client.force_login(user)
        self.assertContains(self.client.get(reverse('my_bookings')), reverse('event_calendar', args=[upcoming.id]))
        booking.cancel()
        self.assertNotContains(self.client.get(reverse('my_bookings')), 'Add to calendar')


class CalendarAttachmentTests(TestCase):
    def test_confirmation_email_has_ics_attachment(self):
        event = make_event(event_name='Jazz Night')
        with self.captureOnCommitCallbacks(execute=True):
            event.book(make_user(), 1)
        (name, content, mimetype), = mail.outbox[0].attachments
        self.assertEqual((name, mimetype), ('jazz-night.ics', 'text/calendar'))
        self.assertIn('SUMMARY:Jazz Night', content)
        self.assertIn('The attached calendar file (.ics)', mail.outbox[0].body)

    def test_cancellation_email_has_no_attachment(self):
        event = make_event()
        booking = event.book(make_user(), 1)
        with self.captureOnCommitCallbacks(execute=True):
            booking.cancel()
        self.assertEqual(mail.outbox[-1].attachments, [])
