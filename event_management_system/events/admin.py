from django.contrib import admin

from .models import Booking, Event


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ('event_name', 'date', 'time', 'venue', 'capacity', 'seats_left', 'price')
    list_filter = ('date', 'venue')
    search_fields = ('event_name', 'venue', 'description')
    date_hierarchy = 'date'
    ordering = ('-date', '-time')

    def get_queryset(self, request):
        return super().get_queryset(request).with_seat_counts()

    @admin.display(description='Seats left', ordering='seats_left')
    def seats_left(self, event):
        return event.seats_left


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('user', 'event', 'number_of_tickets', 'unit_price', 'total', 'status', 'booking_date')
    list_filter = ('status', 'event')
    search_fields = ('user__username', 'user__email', 'event__event_name')
    list_select_related = ('user', 'event')
    ordering = ('-booking_date',)

    @admin.display(description='Total')
    def total(self, booking):
        return booking.total_price
