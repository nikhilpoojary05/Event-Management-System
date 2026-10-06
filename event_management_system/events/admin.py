from django.contrib import admin
from django.db.models import Q, Sum
from django.db.models.functions import Coalesce
from .models import Event, Booking


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ('event_name', 'date', 'time', 'venue', 'capacity', 'seats_left', 'price')
    list_filter = ('date', 'venue')
    search_fields = ('event_name', 'venue', 'description')
    date_hierarchy = 'date'
    ordering = ('-date', '-time')

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            booked=Coalesce(
                Sum('booking__number_of_tickets', filter=Q(booking__status=Booking.Status.BOOKED)), 0
            )
        )

    @admin.display(description='Seats left')
    def seats_left(self, event):
        return event.capacity - event.booked


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('user', 'event', 'number_of_tickets', 'status', 'booking_date')
    list_filter = ('status', 'event')
    search_fields = ('user__username', 'user__email', 'event__event_name')
    list_select_related = ('user', 'event')
    ordering = ('-booking_date',)
