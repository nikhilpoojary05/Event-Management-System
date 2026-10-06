from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, permission_required
from .models import Event, Booking
from .forms import RegisterForm, EventForm, BookingForm
from django.contrib.auth import login, authenticate, logout


def home(request):
    return render(request, 'events/home.html')


def event_list(request):
    events = Event.objects.all()
    return render(request, 'events/event_list.html', {'events': events})


def event_detail(request, event_id):
    event = get_object_or_404(Event, id=event_id)

    total_booked = sum(
        b.number_of_tickets for b in Booking.objects.filter(event=event)
    )
    remaining_seats = event.capacity - total_booked

    return render(request, 'events/event_detail.html', {
        'event': event,
        'remaining_seats': remaining_seats
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
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            return redirect('event_list')
        else:
            return render(request, 'events/login.html', {
                'error': 'Invalid username or password'
            })

    return render(request, 'events/login.html')


def user_logout(request):
    logout(request)
    return redirect('home')


@login_required
def book_event(request, event_id):
    event = get_object_or_404(Event, id=event_id)

    total_booked = sum(
        b.number_of_tickets for b in Booking.objects.filter(event=event)
    )
    remaining_seats = event.capacity - total_booked

    if remaining_seats <= 0:
        return render(request, 'events/book_event.html', {
            'event': event,
            'form': None,
            'error': 'This event is full. Booking is closed.'
        })

    if request.method == 'POST':
        form = BookingForm(request.POST)
        if form.is_valid():
            booking = form.save(commit=False)
            booking.user = request.user
            booking.event = event

            total_booked = sum(
                b.number_of_tickets for b in Booking.objects.filter(event=event)
            )

            if total_booked + booking.number_of_tickets > event.capacity:
                return render(request, 'events/book_event.html', {
                    'form': form,
                    'event': event,
                    'error': 'Not enough seats available!'
                })

            booking.save()
            return redirect('my_bookings')
    else:
        form = BookingForm()

    return render(request, 'events/book_event.html', {
        'form': form,
        'event': event
    })


@login_required
def my_bookings(request):
    bookings = Booking.objects.filter(user=request.user)
    return render(request, 'events/my_bookings.html', {'bookings': bookings})


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
