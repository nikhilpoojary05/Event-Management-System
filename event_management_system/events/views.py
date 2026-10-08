from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import BookingForm, EventFilterForm, EventForm, RegisterForm
from .models import Booking, Event, EventCancelled, EventInPast, NotEnoughSeats
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
    })


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


def user_login(request):
    next_url = request.POST.get('next') or request.GET.get('next', '')
    if not url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        next_url = ''

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            return redirect(next_url or 'event_list')
        else:
            return render(request, 'events/login.html', {
                'error': 'Invalid username or password',
                'next': next_url
            })

    return render(request, 'events/login.html', {'next': next_url})


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
        return closed('This event is full. Booking is closed.')

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
    return render(request, 'events/my_bookings.html', {'bookings': bookings})


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


@login_required
def edit_event(request, event_id):
    event = get_managed_event(request, event_id)
    if event.is_cancelled or event.is_past:
        messages.error(request, 'Cancelled or past events cannot be edited.')
        return redirect('my_events')

    if request.method == 'POST':
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
            if not form.errors:
                messages.success(request, f'Event "{event.event_name}" has been updated.')
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
