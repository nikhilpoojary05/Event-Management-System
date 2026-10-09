from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.core.validators import MaxValueValidator
from django.utils import timezone

from .models import Booking, Event, WaitlistEntry


class RegisterForm(UserCreationForm):
    email = forms.EmailField()

    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2']


class EventForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = ['event_name', 'description', 'date', 'time', 'venue', 'capacity', 'price']
        widgets = {
            'event_name': forms.TextInput(attrs={'placeholder': 'e.g. Campus Tech Fest 2026'}),
            'description': forms.Textarea(attrs={'rows': 5, 'placeholder': 'What should attendees know?'}),
            'date': forms.DateInput(attrs={'type': 'date'}),
            'time': forms.TimeInput(attrs={'type': 'time'}, format='%H:%M'),
            'venue': forms.TextInput(attrs={'placeholder': 'e.g. Main Auditorium'}),
            'capacity': forms.NumberInput(attrs={'placeholder': 'e.g. 100'}),
            'price': forms.NumberInput(attrs={'step': '0.01', 'placeholder': '0 for a free event'}),
        }
        labels = {'event_name': 'Event name', 'price': 'Ticket price (₹)'}
        help_texts = {
            'capacity': 'Maximum number of tickets that can be booked.',
            'price': 'Enter 0 to make the event free.',
        }

    def __init__(self, *args, min_capacity=1, **kwargs):
        super().__init__(*args, **kwargs)
        # When editing, capacity can't drop below the seats already booked.
        self.min_capacity = max(min_capacity, 1)
        self.fields['date'].widget.attrs['min'] = timezone.localdate().isoformat()
        self.fields['capacity'].widget.attrs['min'] = self.min_capacity

    def clean_capacity(self):
        capacity = self.cleaned_data['capacity']
        if capacity < self.min_capacity:
            if self.min_capacity == 1:
                raise forms.ValidationError('Capacity must be at least 1.')
            raise forms.ValidationError(
                f'Capacity cannot be less than the {self.min_capacity} seats already booked.'
            )
        return capacity

    def clean_date(self):
        date = self.cleaned_data['date']
        if date < timezone.localdate():
            raise forms.ValidationError('Event date cannot be in the past.')
        return date


class BookingForm(forms.ModelForm):
    class Meta:
        model = Booking
        fields = ['number_of_tickets']

    def __init__(self, *args, max_tickets=None, **kwargs):
        super().__init__(*args, **kwargs)
        # PositiveIntegerField renders min="0"; the model requires at least 1.
        self.fields['number_of_tickets'].widget.attrs['min'] = 1
        if max_tickets is not None:
            # Browser hint only; Event.book() enforces capacity atomically.
            self.fields['number_of_tickets'].widget.attrs['max'] = max_tickets


class WaitlistForm(forms.ModelForm):
    class Meta:
        model = WaitlistEntry
        fields = ['number_of_tickets']

    def __init__(self, *args, max_tickets=None, **kwargs):
        super().__init__(*args, **kwargs)
        field = self.fields['number_of_tickets']
        field.widget.attrs['min'] = 1
        if max_tickets is not None:
            field.max_value = max_tickets
            field.widget.attrs['max'] = max_tickets
            field.validators.append(MaxValueValidator(max_tickets))


class EventFilterForm(forms.Form):
    """Search and filter options for the event list (submitted via GET)."""

    q = forms.CharField(required=False, max_length=100, label='Search',
                        widget=forms.TextInput(attrs={'type': 'search', 'placeholder': 'Name, venue or description'}))
    date_from = forms.DateField(required=False, label='From', widget=forms.DateInput(attrs={'type': 'date'}))
    date_to = forms.DateField(required=False, label='To', widget=forms.DateInput(attrs={'type': 'date'}))
    free = forms.BooleanField(required=False, label='Free only')
    available = forms.BooleanField(required=False, label='Has seats left')

    def clean(self):
        cleaned = super().clean()
        date_from, date_to = cleaned.get('date_from'), cleaned.get('date_to')
        if date_from and date_to and date_from > date_to:
            self.add_error('date_to', "'To' date must be on or after the 'From' date.")
        return cleaned

    def is_active(self):
        return self.is_valid() and any(self.cleaned_data.values())

    def apply(self, events):
        """Filter an Event queryset (annotated with seat counts) by the valid options."""
        if not self.is_valid():
            return events
        data = self.cleaned_data
        if data['q']:
            events = events.search(data['q'])
        if data['date_from']:
            events = events.filter(date__gte=data['date_from'])
        if data['date_to']:
            events = events.filter(date__lte=data['date_to'])
        if data['free']:
            events = events.filter(price=0)
        if data['available']:
            events = events.filter(seats_left__gt=0, is_cancelled=False)
        return events
