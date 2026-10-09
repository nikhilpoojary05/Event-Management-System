from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.views import LoginView
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.dateformat import format as format_date
from django.utils.dateformat import time_format
from django.views.decorators.http import require_POST

from . import calendar, login_throttle, notifications
from .forms import BookingForm, EventFilterForm, EventForm, RegisterForm, WaitlistForm
from .models import AlreadyWaitlisted, Booking, Event, EventCancelled, EventInPast, NotEnoughSeats, WaitlistEntry
from .templatetags.events_extras import price


def home(request):
    return render(request, 'events/home.html')


EVENTS_PER_PAGE = 10


def event_list(request):
    show_past = request.GET.get('when') == 'past'
    events = Event.objects.with_seat_counts()
    events = events.past() if show_past else events.upcoming()
    filter_form = EventFilterForm(request.GET)
    events = filter_form.apply(events)
    page = Paginator(events, EVENTS_PER_PAGE).get_page(request.GET.get('page'))
    return render(request, 'events/event_list.html', {
        'page': page,
        'events': page.object_list,
        'show_past': show_past,
        'filter_form': filter_form,
        'filtering': filter_form.is_active(),
    })


def event_detail(request, event_id):
    event = get_object_or_404(Event, id=event_id)

    return render(request, 'events/event_detail.html', {
        'event': event,
        'remaining_seats': event.remaining_seats(),
        'can_manage': event.can_manage(request.user),
        'waiting_count': event.waitlist_entries.filter(status=WaitlistEntry.Status.WAITING).count(),
        'my_waitlist_entry': _waitlist_entry_for(request.user, event),
    })


def _waitlist_entry_for(user, event):
    if not user.is_authenticated:
        return None
    return event.waitlist_entries.filter(user=user, status=WaitlistEntry.Status.WAITING).first()


def register(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f'Welcome, {user.username}! Your account has been created.')
            return redirect('event_list')
    else:
        form = RegisterForm()

    return render(request, 'events/register.html', {'form': form})


class LoginForm(AuthenticationForm):
    error_messages = {
        **AuthenticationForm.error_messages,
        'invalid_login': 'Invalid username or password.',
    }


class UserLoginView(LoginView):
    """Django's LoginView (safe ?next= handling, inactive-user checks) plus lockout."""

    template_name = 'events/login.html'
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def post(self, request, *args, **kwargs):
        username = request.POST.get('username', '')
        if login_throttle.is_locked_out(request, username):
            minutes = login_throttle.LOCKOUT_SECONDS // 60
            form = self.get_form()
            form.errors.clear()
            form.add_error(None, f'Too many failed login attempts. Please try again in {minutes} minutes.')
            response = self.render_to_response(self.get_context_data(form=form))
            response.status_code = 429
            return response
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        login_throttle.reset(self.request, form.get_user().get_username())
        return super().form_valid(form)

    def form_invalid(self, form):
        login_throttle.record_failure(self.request, self.request.POST.get('username', ''))
        return super().form_invalid(form)


@require_POST
def user_logout(request):
    logout(request)
    messages.info(request, 'You have been logged out.')
    return redirect('home')


@login_required
def book_event(request, event_id):
    event = get_object_or_404(Event, id=event_id)

    def closed(error):
        return render(request, 'events/book_event.html', {'event': event, 'form': None, 'error': error})

    if event.is_cancelled:
        return closed('This event has been cancelled.')
    if event.is_past:
        return closed('This event has already taken place.')

    remaining_seats = event.remaining_seats()
    if remaining_seats <= 0:
        return render(request, 'events/book_event.html', {
            'event': event,
            'form': None,
            'error': 'This event is full.',
            'waitlist_form': WaitlistForm(max_tickets=event.capacity),
            'my_waitlist_entry': _waitlist_entry_for(request.user, event),
        })

    if request.method == 'POST':
        form = BookingForm(request.POST, max_tickets=remaining_seats)
        if form.is_valid():
            try:
                booking = event.book(request.user, form.cleaned_data['number_of_tickets'])
            except NotEnoughSeats:
                form.add_error(None, 'Not enough seats available!')
            except EventCancelled:
                return closed('This event has been cancelled.')
            except EventInPast:
                return closed('This event has already taken place.')
            else:
                messages.success(
                    request,
                    f'Booked {booking.number_of_tickets} ticket(s) for {event.event_name}. '
                    f'Total: {price(booking.total_price)}.'
                )
                return redirect('my_bookings')
    else:
        form = BookingForm(max_tickets=remaining_seats)

    try:
        tickets = max(int(form['number_of_tickets'].value()), 1)
    except (TypeError, ValueError):
        tickets = 1

    return render(request, 'events/book_event.html', {
        'form': form,
        'event': event,
        'remaining_seats': remaining_seats,
        'total': event.price * tickets,
    })


@login_required
def my_bookings(request):
    bookings = (
        Booking.objects.filter(user=request.user)
        .select_related('event')
        .order_by('-booking_date')
    )
    waitlist = (
        WaitlistEntry.objects.filter(user=request.user, status=WaitlistEntry.Status.WAITING)
        .select_related('event')
        .order_by('event__date')
    )
    return render(request, 'events/my_bookings.html', {'bookings': bookings, 'waitlist': waitlist})


@login_required
@require_POST
def cancel_booking(request, booking_id):
    booking = get_object_or_404(Booking.objects.select_related('event'), id=booking_id, user=request.user)
    if booking.cancel():
        messages.success(request, f'Your booking for {booking.event.event_name} has been cancelled.')
    else:
        messages.error(request, 'This booking can no longer be cancelled.')
    return redirect('my_bookings')


@login_required
@permission_required('events.add_event', raise_exception=True)
def add_event(request):
    if request.method == 'POST':
        form = EventForm(request.POST)
        if form.is_valid():
            event = form.save(commit=False)
            event.organizer = request.user
            event.save()
            messages.success(request, f'Event "{event.event_name}" has been created.')
            return redirect('event_detail', event_id=event.id)
    else:
        form = EventForm()

    return render(request, 'events/add_event.html', {'form': form})


def get_managed_event(request, event_id):
    """Fetch an event the current user may manage, or raise 404/403."""
    event = get_object_or_404(Event, id=event_id)
    if not event.can_manage(request.user):
        raise PermissionDenied
    return event


@login_required
def my_events(request):
    user = request.user
    if not (user.has_perm('events.add_event') or user.has_perm('events.change_event')):
        raise PermissionDenied
    sees_all = user.has_perm('events.change_event')
    events = Event.objects.all() if sees_all else Event.objects.filter(organizer=user)
    events = events.with_seat_counts().with_revenue().select_related('organizer').order_by('-date', '-time')
    page = Paginator(events, 20).get_page(request.GET.get('page'))
    return render(request, 'events/my_events.html', {
        'page': page,
        'events': page.object_list,
        'sees_all': sees_all,
    })


# Changes to these fields are emailed to attendees, formatted for reading.
NOTIFY_ON_CHANGE = {
    'date': ('Date', lambda d: format_date(d, 'l, j F Y')),
    'time': ('Time', lambda t: time_format(t, 'g:i A')),
    'venue': ('Venue', str),
}


@login_required
def edit_event(request, event_id):
    event = get_managed_event(request, event_id)
    if event.is_cancelled or event.is_past:
        messages.error(request, 'Cancelled or past events cannot be edited.')
        return redirect('my_events')

    if request.method == 'POST':
        # Snapshot first: validating a ModelForm writes the new values onto `event`.
        before = {field: getattr(event, field) for field in NOTIFY_ON_CHANGE}
        form = EventForm(request.POST, instance=event, min_capacity=event.booked_seats())
        if form.is_valid():
            with transaction.atomic():
                # Re-check under the same lock Event.book() uses, so a booking
                # made while this form was open can't push capacity below sales.
                booked = Event.objects.select_for_update().get(pk=event.pk).booked_seats()
                if form.cleaned_data['capacity'] < booked:
                    form.add_error('capacity', f'Capacity cannot be less than the {booked} seats already booked.')
                else:
                    form.save()
                    changes = [
                        (label, fmt(before[field]), fmt(getattr(event, field)))
                        for field, (label, fmt) in NOTIFY_ON_CHANGE.items()
                        if before[field] != getattr(event, field)
                    ]
                    if changes:
                        attendees = event.booking_set.filter(status=Booking.Status.BOOKED)
                        notifications.event_updated(event, list(attendees.select_related('user', 'event')), changes)
                    promoted = event.promote_waitlist()  # a capacity increase may free seats
            if not form.errors:
                messages.success(request, f'Event "{event.event_name}" has been updated.')
                if promoted:
                    messages.info(request, f'{len(promoted)} waitlisted booking(s) were confirmed.')
                return redirect('event_detail', event_id=event.id)
    else:
        form = EventForm(instance=event, min_capacity=event.booked_seats())

    return render(request, 'events/edit_event.html', {'form': form, 'event': event})


@login_required
def event_attendees(request, event_id):
    event = get_managed_event(request, event_id)
    bookings = event.booking_set.select_related('user').order_by('status', '-booking_date')
    active = [b for b in bookings if b.status == Booking.Status.BOOKED]
    return render(request, 'events/event_attendees.html', {
        'event': event,
        'bookings': bookings,
        'tickets_sold': sum(b.number_of_tickets for b in active),
        'revenue': sum((b.total_price for b in active), 0),
        'attendee_count': len({b.user_id for b in active}),
        'waitlist': event.waitlist_entries.filter(status=WaitlistEntry.Status.WAITING)
                    .select_related('user').order_by('created_at', 'id'),
    })


@login_required
@require_POST
def cancel_event(request, event_id):
    event = get_managed_event(request, event_id)
    if event.is_cancelled or event.is_past:
        messages.error(request, 'This event can no longer be cancelled.')
    else:
        cancelled = event.cancel()
        messages.success(
            request,
            f'Event "{event.event_name}" has been cancelled, along with {cancelled} booking(s).'
        )
    return redirect('my_events')


@login_required
@require_POST
def join_waitlist(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    form = WaitlistForm(request.POST, max_tickets=event.capacity)
    if not form.is_valid():
        messages.error(request, ' '.join(form.errors.get('number_of_tickets', ['Invalid number of tickets.'])))
        return redirect('book_event', event_id=event.id)
    try:
        entry = event.join_waitlist(request.user, form.cleaned_data['number_of_tickets'])
    except AlreadyWaitlisted:
        messages.info(request, "You're already on the waitlist for this event.")
        return redirect('my_bookings')
    except (EventCancelled, EventInPast):
        messages.error(request, 'This event is no longer taking bookings.')
        return redirect('event_detail', event_id=event.id)

    if entry.status == WaitlistEntry.Status.BOOKED:
        messages.success(request, f'Seats were available, so we booked {entry.number_of_tickets} ticket(s) for you.')
    else:
        messages.success(
            request,
            f"You're #{entry.position} on the waitlist for {event.event_name}. "
            "We'll book your seats automatically and email you if they free up."
        )
    return redirect('my_bookings')


@login_required
@require_POST
def leave_waitlist(request, entry_id):
    entry = get_object_or_404(WaitlistEntry.objects.select_related('event'), id=entry_id, user=request.user)
    if entry.leave():
        messages.success(request, f'You have left the waitlist for {entry.event.event_name}.')
    else:
        messages.error(request, 'You are no longer on this waitlist.')
    return redirect('my_bookings')


def event_calendar(request, event_id):
    """Download the event as an .ics file for Google Calendar, Outlook, Apple Calendar, etc."""
    event = get_object_or_404(Event, id=event_id)
    response = HttpResponse(calendar.build_ics(event), content_type='text/calendar; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{calendar.filename(event)}"'
    return response
