from django.db import models


class WorkerProfile(models.Model):
    user = models.OneToOneField(
        'users.User', on_delete=models.CASCADE, related_name='worker_profile'
    )
    max_morning_shift_hours = models.DecimalField(max_digits=4, decimal_places=2, default=7.5)
    max_afternoon_shift_hours = models.DecimalField(max_digits=4, decimal_places=2, default=7.0)
    max_break_minutes = models.PositiveIntegerField(default=30)
    works_monday = models.BooleanField(default=True)
    works_tuesday = models.BooleanField(default=True)
    works_wednesday = models.BooleanField(default=True)
    works_thursday = models.BooleanField(default=True)
    works_friday = models.BooleanField(default=True)
    works_saturday = models.BooleanField(default=False)
    works_sunday = models.BooleanField(default=False)
    vacation_days_per_year = models.PositiveIntegerField(default=30)
    vacation_days_used = models.PositiveIntegerField(default=0)
    send_shift_limit_email = models.BooleanField(default=True)
    send_break_limit_email = models.BooleanField(default=True)
    send_monthly_report_email = models.BooleanField(default=True)
    monthly_report_day = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Perfil laboral'
        verbose_name_plural = 'Perfiles laborales'

    def __str__(self):
        return f'Perfil de {self.user.username}'

    @property
    def vacation_days_remaining(self):
        return max(0, self.vacation_days_per_year - self.vacation_days_used)

    @property
    def max_shift_seconds(self):
        from django.utils import timezone
        now = timezone.localtime(timezone.now())
        if now.hour < 14:
            return int(float(self.max_morning_shift_hours) * 3600)
        return int(float(self.max_afternoon_shift_hours) * 3600)

    @property
    def max_break_seconds(self):
        return self.max_break_minutes * 60


class MedicalLeave(models.Model):
    user = models.ForeignKey(
        'users.User', on_delete=models.CASCADE, related_name='medical_leaves'
    )
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    reason = models.TextField(blank=True)
    document = models.ImageField(upload_to='medical_leaves/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Baja medica'
        verbose_name_plural = 'Bajas medicas'
        ordering = ['-start_date']

    def __str__(self):
        return f'Baja {self.user.username} desde {self.start_date}'


class VacationPeriod(models.Model):
    user = models.ForeignKey(
        'users.User', on_delete=models.CASCADE, related_name='vacation_periods'
    )
    start_date = models.DateField()
    end_date = models.DateField()
    notes = models.TextField(blank=True)
    approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Periodo de vacaciones'
        verbose_name_plural = 'Periodos de vacaciones'
        ordering = ['-start_date']

    def __str__(self):
        return f'Vacaciones {self.user.username}: {self.start_date} - {self.end_date}'

    @property
    def days_count(self):
        return (self.end_date - self.start_date).days + 1


class LaborAbsence(models.Model):
    class AbsenceType(models.TextChoices):
        UNJUSTIFIED = "UNJUSTIFIED", "Ausencia injustificada"
        PERSONAL = "PERSONAL", "Asunto personal"
        FAMILY = "FAMILY", "Familiar"
        OTHER = "OTHER", "Otro"

    user = models.ForeignKey(
        'users.User', on_delete=models.CASCADE, related_name='labor_absences'
    )
    absence_type = models.CharField(max_length=20, choices=AbsenceType.choices, default=AbsenceType.OTHER)
    date = models.DateField()
    reason = models.TextField(blank=True)
    approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Ausencia laboral'
        verbose_name_plural = 'Ausencias laborales'
        ordering = ['-date']

    def __str__(self):
        return f'Ausencia {self.user.username} - {self.date}'
