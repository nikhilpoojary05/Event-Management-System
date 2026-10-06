from django.db import models
from django.contrib.auth.models import User


class Event(models.Model):
    event_name = models.CharField(max_length=200)
    description = models.TextField()
    date = models.DateField()
    time = models.TimeField()
    venue = models.CharField(max_length=200)
    capacity = models.IntegerField()
    price = models.DecimalField(max_digits=8, decimal_places=2, default=0.00)

    def __str__(self):
        return self.event_name


class Booking(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    booking_date = models.DateTimeField(auto_now_add=True)
    number_of_tickets = models.IntegerField(default=1)
    status = models.CharField(max_length=20, default='Booked')

    def __str__(self):
        return f"{self.user.username} - {self.event.event_name}"