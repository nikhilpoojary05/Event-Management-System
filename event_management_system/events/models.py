from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.db.models import Sum
from django.contrib.auth.models import User


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

    def __str__(self):
        return self.event_name

    def booked_seats(self):
        return self.booking_set.aggregate(total=Sum('number_of_tickets'))['total'] or 0

    def remaining_seats(self):
        return self.capacity - self.booked_seats()

    def book(self, user, number_of_tickets):
        """Create a booking, or raise NotEnoughSeats.

        The seat check and insert run in one transaction with the event row
        locked, so concurrent requests can't both take the last seats.
        """
        with transaction.atomic():
            event = Event.objects.select_for_update().get(pk=self.pk)
            if number_of_tickets > event.remaining_seats():
                raise NotEnoughSeats
            return Booking.objects.create(
                user=user, event=event, number_of_tickets=number_of_tickets
            )


class NotEnoughSeats(Exception):
    pass


class Booking(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    booking_date = models.DateTimeField(auto_now_add=True)
    number_of_tickets = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    status = models.CharField(max_length=20, default='Booked')

    def __str__(self):
        return f"{self.user.username} - {self.event.event_name}"