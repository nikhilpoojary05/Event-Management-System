from django.urls import path

from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('events/', views.event_list, name='event_list'),
    path('event/<int:event_id>/', views.event_detail, name='event_detail'),
    path('event/<int:event_id>/calendar.ics', views.event_calendar, name='event_calendar'),
    path('register/', views.register, name='register'),
    path('login/', views.UserLoginView.as_view(), name='login'),
    path('logout/', views.user_logout, name='logout'),
    path('book/<int:event_id>/', views.book_event, name='book_event'),
    path('my-bookings/', views.my_bookings, name='my_bookings'),
    path('bookings/<int:booking_id>/cancel/', views.cancel_booking, name='cancel_booking'),
    path('add-event/', views.add_event, name='add_event'),
    path('my-events/', views.my_events, name='my_events'),
    path('event/<int:event_id>/edit/', views.edit_event, name='edit_event'),
    path('event/<int:event_id>/attendees/', views.event_attendees, name='event_attendees'),
    path('event/<int:event_id>/cancel/', views.cancel_event, name='cancel_event'),
    path('event/<int:event_id>/waitlist/', views.join_waitlist, name='join_waitlist'),
    path('waitlist/<int:entry_id>/leave/', views.leave_waitlist, name='leave_waitlist'),
]
