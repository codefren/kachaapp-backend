from django.contrib import admin
from .models import WorkerProfile, MedicalLeave, VacationPeriod


@admin.register(WorkerProfile)
class WorkerProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'max_morning_shift_hours', 'max_afternoon_shift_hours', 'max_break_minutes', 'vacation_days_per_year')
    search_fields = ('user__username',)


@admin.register(MedicalLeave)
class MedicalLeaveAdmin(admin.ModelAdmin):
    list_display = ('user', 'start_date', 'end_date', 'reason')
    search_fields = ('user__username',)


@admin.register(VacationPeriod)
class VacationPeriodAdmin(admin.ModelAdmin):
    list_display = ('user', 'start_date', 'end_date', 'approved')
    search_fields = ('user__username',)
