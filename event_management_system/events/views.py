from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, permission_required
from .models import Event, Booking, NotEnoughSeats
from .forms import RegisterForm, EventForm, BookingForm
from django.contrib.auth import login, authenticate, logout
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST


def home(request):
    return render(request, 'events/home.html')


def event_list(request):
    events = Event.objects.all()
    return render(request, 'events/event_list.html', {'events': events})


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
    return redirect('home')


@login_required
def book_event(request, event_id):
    event = get_object_or_404(Event, id=event_id)

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
                event.book(request.user, form.cleaned_data['number_of_tickets'])
            except NotEnoughSeats:
                return render(request, 'events/book_event.html', {
                    'form': form,
                    'event': event,
                    'error': 'Not enough seats available!'
                })

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
    booking.cancel()
    return redirect('my_bookings')


@login_required
@permission_required('events.add_event', raise_exception=True)
def add_event(request):
    if request.method == 'POST':
        form = EventForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('event_list')
    else:
        form = EventForm()

    return render(request, 'events/add_event.html', {'form': form})
