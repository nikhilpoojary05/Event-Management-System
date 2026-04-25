from django.contrib import admin
from .models import Instructor, Student, Course


@admin.register(Instructor)
class InstructorAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'email', 'experience')
    search_fields = ('name', 'email')


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'age', 'email', 'enrollment_year', 'enrollment_date')
    search_fields = ('name', 'email')
    list_filter = ('enrollment_year',)


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'instructor')
    search_fields = ('title', 'instructor__name')
    filter_horizontal = ('students',)