from django.db import models
from django.contrib.auth.models import User


# ===============================
# Instructor Model
# ===============================
class Instructor(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    experience = models.PositiveIntegerField(help_text="Experience in years")

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.experience} yrs)"

    class Meta:
        ordering = ['name']


# ===============================
# Student Model
# ===============================
class Student(models.Model):
    name = models.CharField(max_length=100)
    age = models.PositiveIntegerField()
    email = models.EmailField(unique=True)
    enrollment_year = models.PositiveIntegerField()
    enrollment_date = models.DateField()

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} - {self.email}"

    class Meta:
        ordering = ['name']


# ===============================
# Course Model
# ===============================
class Course(models.Model):
    title = models.CharField(max_length=100)
    description = models.TextField()

    instructor = models.ForeignKey(
        Instructor,
        on_delete=models.CASCADE,
        related_name='courses'
    )

    students = models.ManyToManyField(
        Student,
        related_name='courses',
        blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

    # 🔥 Extra helper method
    def total_students(self):
        return self.students.count()

    class Meta:
        ordering = ['title']


# ===============================
# Event Management Models
# ===============================
class Event(models.Model):
    event_name = models.CharField(max_length=200)
    description = models.TextField()
    date = models.DateField()
    time = models.TimeField()
    venue = models.CharField(max_length=200)
    capacity = models.IntegerField()
    price = models.DecimalField(max_digits=8, decimal_places=2, default=0.0)

    def __str__(self):
        return self.event_name


class Booking(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    booking_date = models.DateTimeField(auto_now_add=True)
    number_of_tickets = models.IntegerField(default=1)
    status = models.CharField(max_length=20, default='Booked')

    def __str__(self):
        return f"{self.user.username} - {self.event.event_name} ({self.number_of_tickets})"