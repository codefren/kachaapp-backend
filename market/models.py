from django.db import models
from django.core.exceptions import ValidationError
from .utils import haversine_distance

from django.conf import settings
from django.utils import timezone


class Market(models.Model):
    name = models.CharField(max_length=255)
    organization = models.ForeignKey(
        'users.Organization',
        on_delete=models.PROTECT,
        related_name='markets',
        null=True,
        blank=True,
        help_text="Organización a la que pertenece el mercado"
    )
    latitude = models.FloatField()
    longitude = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('organization', 'name')]

    def __str__(self):
        org_name = self.organization.name if self.organization else 'Sin org'
        return f"{self.name} ({org_name})"

    def is_near(self, user_lat, user_lon, max_distance_meters=500):
        distancia = haversine_distance(
            self.latitude, self.longitude, user_lat, user_lon
        )
        return distancia <= max_distance_meters


class LoginHistory(models.Model):
    LOGIN = "login"
    REFRESH = "refresh"
    EVENT_TYPE_CHOICES = [
        (LOGIN, "Login"),
        (REFRESH, "Refresh"),
    ]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    market = models.ForeignKey(Market, on_delete=models.CASCADE)
    latitude = models.FloatField()
    longitude = models.FloatField()
    event_type = models.CharField(max_length=10, choices=EVENT_TYPE_CHOICES)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} - {self.market} - {self.event_type} - {self.timestamp}"


class Refrigerator(models.Model):
    market = models.ForeignKey(
        Market, related_name="refrigerators", on_delete=models.CASCADE
    )
    name = models.CharField(max_length=80)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("market", "name")
        verbose_name = "Refrigerator"
        verbose_name_plural = "Refrigerators"

    def __str__(self):
        return f"{self.market.name} | {self.name}"


class TemperatureRecord(models.Model):
    class Period(models.TextChoices):
        MORNING = "MORNING", "Mañana"
        NIGHT = "NIGHT", "Noche"

    refrigerator = models.ForeignKey(
        Refrigerator,
        related_name="temperature_records",
        on_delete=models.CASCADE,
    )
    date = models.DateField()
    period = models.CharField(
        max_length=10,
        choices=Period.choices,
        help_text="Período del día para el registro de temperatura",
    )
    temperature = models.FloatField(help_text="Temperatura en grados Celsius")
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("refrigerator", "date", "period")
        ordering = ["-date", "period"]
        verbose_name = "Temperature Record"
        verbose_name_plural = "Temperature Records"
        constraints = [
            models.CheckConstraint(
                check=models.Q(temperature__gte=-30.0)
                & models.Q(temperature__lte=10.0),
                name="temperature_range_check",
            ),
        ]

    def clean(self):
        super().clean()
        if self.temperature is not None:
            if self.temperature < -30.0 or self.temperature > 10.0:
                raise ValidationError(
                    {
                        "temperature": "La temperatura debe estar entre -30°C y 10°C para una nevera."
                    }
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def is_temperature_critical(self):
        if self.temperature is None:
            return False
        return self.temperature > 5.0 or self.temperature < -25.0

    def get_temperature_status(self):
        if self.temperature is None:
            return "UNKNOWN"

        if self.temperature > 10.0 or self.temperature < -30.0:
            return "INVALID"
        elif self.temperature > 5.0:
            return "HIGH"
        elif self.temperature < -25.0:
            return "VERY_LOW"
        elif self.temperature >= -5.0 and self.temperature <= 3.0:
            return "OPTIMAL"
        else:
            return "NORMAL"

    @classmethod
    def get_critical_temperatures(cls, refrigerator=None, days=7):
        queryset = cls.objects.all()
        if refrigerator:
            queryset = queryset.filter(refrigerator=refrigerator)

        since_date = timezone.now().date() - timezone.timedelta(days=days)
        queryset = queryset.filter(date__gte=since_date)

        return queryset.filter(
            models.Q(temperature__gt=5.0) | models.Q(temperature__lt=-25.0)
        )

    def __str__(self):
        period_display = dict(self.Period.choices).get(self.period, self.period)
        status = self.get_temperature_status()
        return f"{self.refrigerator} - {self.date} ({period_display}): {self.temperature}°C [{status}]"


class Shift(models.Model):
    class Status(models.TextChoices):
        WORKING = "WORKING", "Working"
        BREAK = "BREAK", "Break"
        OFF = "OFF", "Off"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="shifts",
    )
    market = models.ForeignKey(
        Market,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="shifts",
    )

    started_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)

    break_started_at = models.DateTimeField(null=True, blank=True)
    break_total_seconds = models.PositiveIntegerField(default=0)

    start_latitude = models.FloatField(null=True, blank=True)
    last_latitude = models.FloatField(null=True, blank=True)
    last_longitude = models.FloatField(null=True, blank=True)
    last_location_at = models.DateTimeField(null=True, blank=True)
    out_of_range_since = models.DateTimeField(null=True, blank=True)
    start_longitude = models.FloatField(null=True, blank=True)

    end_latitude = models.FloatField(null=True, blank=True)
    end_longitude = models.FloatField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.user} | {self.started_at} | {self.ended_at or 'OPEN'}"

    @property
    def is_open(self):
        return self.ended_at is None

    @property
    def on_break(self):
        return self.break_started_at is not None and self.ended_at is None

    def get_break_seconds(self, now=None):
        total = int(self.break_total_seconds or 0)

        if self.break_started_at and self.ended_at is None:
            now = now or timezone.now()
            extra = max(0, int((now - self.break_started_at).total_seconds()))
            total += extra

        return total

    def get_worked_seconds(self, now=None):
        now = now or timezone.now()

        if self.ended_at:
            total_span = max(0, int((self.ended_at - self.started_at).total_seconds()))
        else:
            total_span = max(0, int((now - self.started_at).total_seconds()))

        break_seconds = self.get_break_seconds(now=now)
        return max(0, total_span - break_seconds)

    def close_break(self, now=None):
        if not self.break_started_at:
            return

        now = now or timezone.now()
        extra = max(0, int((now - self.break_started_at).total_seconds()))
        self.break_total_seconds = int(self.break_total_seconds or 0) + extra
        self.break_started_at = None

    def close_shift(self, now=None):
        now = now or timezone.now()

        if self.break_started_at:
            self.close_break(now=now)

        self.ended_at = now
