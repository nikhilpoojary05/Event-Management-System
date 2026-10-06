from django.core.paginator import Paginator
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from .models import Event, Booking, EventInPast, NotEnoughSeats
from .forms import RegisterForm, EventForm, BookingForm
from django.contrib.auth import login, authenticate, logout
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST


def home(request):
    return render(request, 'events/home.html')


EVENTS_PER_PAGE = 10


def event_list(request):
    show_past = request.GET.get('when') == 'past'
    events = Event.objects.with_seat_counts()
    events = events.past() if show_past else events.upcoming()
    page = Paginator(events, EVENTS_PER_PAGE).get_page(request.GET.get('page'))
    return render(request, 'events/event_list.html', {
        'page': page,
        'events': page.object_list,
        'show_past': show_past,
    })


def event_detail(request, event_id):
    event = get_object_or_404(Event, id=event_id)

    return render(request, 'events/event_detail.html', {
        'event': event,
        'remaining_seats': event.remaining_seats()
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


def user_logout(request):
    logout(request)
    messages.info(request, 'You have been logged out.')
    return redirect('home')


@login_required
def book_event(request, event_id):
    event = get_object_or_404(Event, id=event_id)

    if event.is_past:
        return render(request, 'events/book_event.html', {
            'event': event,
            'form': None,
            'error': 'This event has already taken place.'
        })

    if event.remaining_seats() <= 0:
        return render(request, 'events/book_event.html', {
            'event': event,
            'form': None,
            'error': 'This event is full. Booking is closed.'
        })

    if request.method == 'POST':
        form = BookingForm(request.POST)
        if form.is_valid():
            try:
                booking = event.book(request.user, form.cleaned_data['number_of_tickets'])
            except NotEnoughSeats:
                return render(request, 'events/book_event.html', {
                    'form': form,
                    'event': event,
                    'error': 'Not enough seats available!'
                })
            except EventInPast:
                return render(request, 'events/book_event.html', {
                    'event': event,
                    'form': None,
                    'error': 'This event has already taken place.'
                })

            messages.success(
                request,
                f'Booked {booking.number_of_tickets} ticket(s) for {event.event_name}.'
            )
            return redirect('my_bookings')
    else:
        form = BookingForm()

    return render(request, 'events/book_event.html', {
        'form': form,
        'event': event
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
            event = form.save()
            messages.success(request, f'Event "{event.event_name}" has been created.')
            return redirect('event_detail', event_id=event.id)
    else:
        form = EventForm()

    return render(request, 'events/add_event.html', {'form': form})
