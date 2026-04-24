from django.contrib import admin
from .models import WorkerProfile, MedicalLeave, VacationPeriod, LaborAbsence


@admin.register(WorkerProfile)
class WorkerProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'max_morning_shift_hours', 'max_afternoon_shift_hours', 'max_break_minutes', 'auto_checkin_enabled', 'vacation_days_remaining')
    search_fields = ('user__username',)
    actions = ['copy_monday_to_all']

    fieldsets = (
        ('Usuario', {'fields': ('user',)}),
        ('Límites de jornada', {'fields': ('max_morning_shift_hours', 'max_afternoon_shift_hours', 'max_break_minutes')}),
        ('Fichaje automático', {'fields': ('auto_checkin_enabled', 'checkin_tolerance_minutes')}),
        ('Horario Lunes', {'fields': ('monday_start', 'monday_end')}),
        ('Horario Martes', {'fields': ('tuesday_start', 'tuesday_end')}),
        ('Horario Miércoles', {'fields': ('wednesday_start', 'wednesday_end')}),
        ('Horario Jueves', {'fields': ('thursday_start', 'thursday_end')}),
        ('Horario Viernes', {'fields': ('friday_start', 'friday_end')}),
        ('Horario Sábado', {'fields': ('saturday_start', 'saturday_end')}),
        ('Horario Domingo', {'fields': ('sunday_start', 'sunday_end')}),
        ('Días laborables', {'fields': ('works_monday', 'works_tuesday', 'works_wednesday', 'works_thursday', 'works_friday', 'works_saturday', 'works_sunday')}),
        ('Vacaciones', {'fields': ('vacation_days_per_year', 'vacation_days_used')}),
        ('Emails', {'fields': ('send_shift_limit_email', 'send_break_limit_email', 'send_monthly_report_email', 'monthly_report_day')}),
    )

    @admin.display(description='Días vacaciones restantes')
    def vacation_days_remaining(self, obj):
        return obj.vacation_days_remaining

    @admin.action(description='Copiar horario del lunes a todos los días')
    def copy_monday_to_all(self, request, queryset):
        updated = 0
        for profile in queryset:
            if profile.monday_start and profile.monday_end:
                for day in ['tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']:
                    setattr(profile, f'{day}_start', profile.monday_start)
                    setattr(profile, f'{day}_end', profile.monday_end)
                profile.save()
                updated += 1
        self.message_user(request, f'Horario copiado a {updated} perfil(es).')


@admin.register(MedicalLeave)
class MedicalLeaveAdmin(admin.ModelAdmin):
    list_display = ('user', 'start_date', 'end_date', 'reason')
    search_fields = ('user__username',)


@admin.register(VacationPeriod)
class VacationPeriodAdmin(admin.ModelAdmin):
    list_display = ('user', 'start_date', 'end_date', 'approved')
    search_fields = ('user__username',)


@admin.register(LaborAbsence)
class LaborAbsenceAdmin(admin.ModelAdmin):
    list_display = ('user', 'date', 'absence_type', 'approved')
    list_filter = ('absence_type', 'approved')
    search_fields = ('user__username',)
