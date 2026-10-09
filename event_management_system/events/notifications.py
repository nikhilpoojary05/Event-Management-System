"""Email notifications for bookings and events.

Each function schedules its emails with transaction.on_commit, so nothing is
sent if the surrounding database change is rolled back. Delivery failures are
logged rather than raised, so a mail outage never breaks a booking.
"""
import logging

from django.conf import settings
from django.core.mail import send_mass_mail
from django.db import transaction
from django.template.loader import render_to_string
from django.urls import reverse

logger = logging.getLogger(__name__)


def _url(name, *args):
    return settings.SITE_URL + reverse(name, args=args)


def _message(template, subject, user, event, **extra):
    if not user.email:
        return None
    context = {
        'event': event,
        'name': user.get_full_name() or user.username,
        'event_url': _url('event_detail', event.id),
        'bookings_url': _url('my_bookings'),
        **extra,
    }
    body = render_to_string(f'events/email/{template}.txt', context)
    return (subject, body, settings.DEFAULT_FROM_EMAIL, [user.email])


def _booking_message(template, subject, booking, **extra):
    return _message(template, f'{subject}: {booking.event.event_name}', booking.user, booking.event,
                    booking=booking, **extra)


def _send_on_commit(build_messages):
    def send():
        messages = [m for m in build_messages() if m]
        if not messages:
            return
        try:
            send_mass_mail(messages, fail_silently=False)
        except Exception:
            logger.exception('Failed to send %d notification email(s)', len(messages))

    transaction.on_commit(send)


def booking_confirmed(booking):
    _send_on_commit(lambda: [
        _booking_message('booking_confirmed', 'Booking confirmed', booking),
    ])


def booking_cancelled(booking):
    _send_on_commit(lambda: [
        _booking_message('booking_cancelled', 'Booking cancelled', booking),
    ])


def event_cancelled(event, bookings):
    _send_on_commit(lambda: [
        _booking_message('event_cancelled', 'Event cancelled', booking)
        for booking in bookings
    ])


def event_updated(event, bookings, changes):
    """changes: list of (label, old value, new value) for the fields attendees care about."""
    _send_on_commit(lambda: [
        _booking_message('event_updated', 'Event updated', booking, changes=changes)
        for booking in bookings
    ])


def waitlist_promoted(bookings):
    """Bookings just created from the waitlist."""
    if not bookings:
        return
    _send_on_commit(lambda: [
        _booking_message('waitlist_promoted', "You're in", booking)
        for booking in bookings
    ])


def waitlist_event_cancelled(event, entries):
    if not entries:
        return
    _send_on_commit(lambda: [
        _message('waitlist_event_cancelled', f'Event cancelled: {event.event_name}', entry.user, event, entry=entry)
        for entry in entries
    ])
