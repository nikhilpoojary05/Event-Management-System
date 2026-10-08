from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.utils import timezone

from .models import Booking, Event


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
            'date': forms.DateInput(attrs={'type': 'date'}),
            'time': forms.TimeInput(attrs={'type': 'time'}, format='%H:%M'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['date'].widget.attrs['min'] = timezone.localdate().isoformat()
        self.fields['capacity'].widget.attrs['min'] = 1

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
