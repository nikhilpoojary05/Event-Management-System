from django.contrib import admin

from .models import Booking, Event


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ('event_name', 'date', 'time', 'venue', 'organizer', 'capacity', 'seats_left', 'price',
                    'is_cancelled')
    list_filter = ('is_cancelled', 'date', 'venue')
    list_select_related = ('organizer',)
    autocomplete_fields = ('organizer',)
    # Cancelling must also cancel bookings, so it goes through the action below, not a checkbox.
    readonly_fields = ('is_cancelled',)
    actions = ['cancel_events']
    search_fields = ('event_name', 'venue', 'description')
    date_hierarchy = 'date'
    ordering = ('-date', '-time')

    def get_queryset(self, request):
        return super().get_queryset(request).with_seat_counts()

    @admin.display(description='Seats left', ordering='seats_left')
    def seats_left(self, event):
        return event.seats_left

    @admin.action(description='Cancel selected events (and their bookings)')
    def cancel_events(self, request, queryset):
        events = bookings = 0
        for event in queryset:
            if not (event.is_cancelled or event.is_past):
                bookings += event.cancel()
                events += 1
        self.message_user(request, f'Cancelled {events} event(s) and {bookings} booking(s).')


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
