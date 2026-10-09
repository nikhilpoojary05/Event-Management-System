"""Build iCalendar (.ics, RFC 5545) files so attendees can add events to their calendars."""
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone

from django.conf import settings
from django.urls import reverse
from django.utils import timezone

# Events have a start time but no end time; assume this duration.
DEFAULT_DURATION = timedelta(hours=2)


def _escape(text):
    return (
        str(text).replace('\\', '\\\\').replace(';', '\\;').replace(',', '\\,')
        .replace('\r\n', '\\n').replace('\n', '\\n')
    )


def _fold(line):
    """Fold lines longer than 75 octets, as the spec requires (continuations start with a space)."""
    if len(line.encode('utf-8')) <= 75:
        return line
    parts, current = [], b''
    for char in line:
        encoded = char.encode('utf-8')
        limit = 75 if not parts else 74  # continuation lines spend one octet on the leading space
        if len(current) + len(encoded) > limit:
            parts.append(current.decode('utf-8'))
            current = b''
        current += encoded
    parts.append(current.decode('utf-8'))
    return '\r\n '.join(parts)


def _utc(value):
    return value.astimezone(dt_timezone.utc).strftime('%Y%m%dT%H%M%SZ')


def event_start(event):
    return timezone.make_aware(datetime.combine(event.date, event.time))


def build_ics(event):
    start = event_start(event)
    host = settings.SITE_URL.split('://', 1)[-1].split('/')[0] or 'localhost'
    url = settings.SITE_URL + reverse('event_detail', args=[event.pk])
    lines = [
        'BEGIN:VCALENDAR',
        'VERSION:2.0',
        'PRODID:-//Event Management System//EN',
        'CALSCALE:GREGORIAN',
        'METHOD:PUBLISH',
        'BEGIN:VEVENT',
        f'UID:event-{event.pk}@{host}',
        f'DTSTAMP:{_utc(timezone.now())}',
        f'DTSTART:{_utc(start)}',
        f'DTEND:{_utc(start + DEFAULT_DURATION)}',
        f'SUMMARY:{_escape(event.event_name)}',
        f'LOCATION:{_escape(event.venue)}',
        f'DESCRIPTION:{_escape(event.description)}',
        f'URL:{url}',
        f"STATUS:{'CANCELLED' if event.is_cancelled else 'CONFIRMED'}",
        'END:VEVENT',
        'END:VCALENDAR',
    ]
    return '\r\n'.join(_fold(line) for line in lines) + '\r\n'


def filename(event):
    safe = ''.join(c if c.isalnum() else '-' for c in event.event_name).strip('-').lower() or 'event'
    return f'{safe[:50]}.ics'
