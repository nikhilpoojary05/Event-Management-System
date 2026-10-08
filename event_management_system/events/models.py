from decimal import Decimal

from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.db.models import DecimalField, F, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone


class EventQuerySet(models.QuerySet):
    def upcoming(self):
        return self.filter(date__gte=timezone.localdate()).order_by('date', 'time')

    def past(self):
        return self.filter(date__lt=timezone.localdate()).order_by('-date', '-time')

    def search(self, text):
        """Events whose name, venue or description contain every word of text."""
        qs = self
        for word in text.split():
            qs = qs.filter(
                Q(event_name__icontains=word) | Q(venue__icontains=word) | Q(description__icontains=word)
            )
        return qs

    def with_seat_counts(self):
        """Annotate booked_count and seats_left in the same query."""
        return self.annotate(
            booked_count=Coalesce(
                Sum('booking__number_of_tickets', filter=Q(booking__status=Booking.Status.BOOKED)), 0
            ),
            seats_left=F('capacity') - F('booked_count'),
        )

    def with_revenue(self):
        """Annotate revenue: the total price of active bookings."""
        money = DecimalField(max_digits=12, decimal_places=2)
        return self.annotate(
            revenue=Coalesce(
                Sum(
                    F('booking__unit_price') * F('booking__number_of_tickets'),
                    filter=Q(booking__status=Booking.Status.BOOKED),
                    output_field=money,
                ),
                Value(Decimal('0.00')),
                output_field=money,
            )
        )


class Event(models.Model):
    event_name = models.CharField(max_length=200)
    description = models.TextField()
    date = models.DateField()
    time = models.TimeField()
    venue = models.CharField(max_length=200)
    capacity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    price = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    organizer = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='organized_events'
    )
    is_cancelled = models.BooleanField(default=False)

    objects = EventQuerySet.as_manager()

    def __str__(self):
        return self.event_name

    @property
    def is_past(self):
        return self.date < timezone.localdate()

    def can_manage(self, user):
        """Organizers manage their own events; users with change_event (admins) manage all."""
        if not user.is_authenticated:
            return False
        return self.organizer_id == user.id or user.has_perm('events.change_event')

    def booked_seats(self):
        return self.booking_set.filter(status=Booking.Status.BOOKED).aggregate(
            total=Sum('number_of_tickets')
        )['total'] or 0

    def remaining_seats(self):
        return self.capacity - self.booked_seats()

    def book(self, user, number_of_tickets):
        """Create a booking, or raise EventCancelled / EventInPast / NotEnoughSeats.

        The seat check and insert run in one transaction with the event row
        locked, so concurrent requests can't both take the last seats.
        """
        with transaction.atomic():
            event = Event.objects.select_for_update().get(pk=self.pk)
            if event.is_cancelled:
                raise EventCancelled
            if event.is_past:
                raise EventInPast
            if number_of_tickets > event.remaining_seats():
                raise NotEnoughSeats
            return Booking.objects.create(
                user=user, event=event, number_of_tickets=number_of_tickets, unit_price=event.price
            )

    def cancel(self):
        """Cancel the event and all its active bookings. Returns the number of bookings cancelled."""
        with transaction.atomic():
            event = Event.objects.select_for_update().get(pk=self.pk)
            if event.is_cancelled or event.is_past:
                return 0
            event.is_cancelled = True
            event.save(update_fields=['is_cancelled'])
            self.is_cancelled = True
            return event.booking_set.filter(status=Booking.Status.BOOKED).update(
                status=Booking.Status.CANCELLED
            )


class BookingError(Exception):
    pass


class NotEnoughSeats(BookingError):
    pass


class EventInPast(BookingError):
    pass


class EventCancelled(BookingError):
    pass


class Booking(models.Model):
    class Status(models.TextChoices):
        BOOKED = 'Booked', 'Booked'
        CANCELLED = 'Cancelled', 'Cancelled'

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    booking_date = models.DateTimeField(auto_now_add=True)
    number_of_tickets = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.BOOKED)
    # Ticket price when booked, so later changes to the event's price don't alter past bookings.
    unit_price = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))]
    )

    def __str__(self):
        return f"{self.user.username} - {self.event.event_name}"

    @property
    def total_price(self):
        return self.unit_price * self.number_of_tickets

    @property
    def can_cancel(self):
        return self.status == self.Status.BOOKED and not self.event.is_past

    def cancel(self):
        """Cancel this booking, freeing its seats. Returns False if not allowed."""
        if not self.can_cancel:
            return False
        self.status = self.Status.CANCELLED
        self.save(update_fields=['status'])
        return True
