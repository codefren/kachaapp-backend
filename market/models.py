from django.db import models
from django.core.exceptions import ValidationError
from .utils import haversine_distance

from django.conf import settings


class Market(models.Model):
    name = models.CharField(max_length=255, unique=True)
    latitude = models.FloatField()
    longitude = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    def is_near(self, user_lat, user_lon, max_distance_meters=500):
        """
        Retorna True si el usuario está a max_distance_meters o menos de la tienda.
        """
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
    """Nevera perteneciente a un market."""

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
    """Registro de temperatura de una nevera (mañana y noche)."""

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
        """Validar que la temperatura esté en un rango apropiado para neveras."""
        super().clean()
        if self.temperature is not None:
            # Validación de rango normal para neveras
            if self.temperature < -30.0 or self.temperature > 10.0:
                raise ValidationError(
                    {
                        "temperature": "La temperatura debe estar entre -30°C y 10°C para una nevera."
                    }
                )

            # Validación de alerta: temperatura crítica
            if self.temperature > 5.0:
                # No bloquear, pero podría usarse para alertas
                pass  # Temperatura alta pero no crítica

            if self.temperature < -25.0:
                # No bloquear, pero podría usarse para alertas
                pass  # Temperatura muy baja pero no crítica

    def save(self, *args, **kwargs):
        """Ejecutar validaciones antes de guardar."""
        self.full_clean()
        super().save(*args, **kwargs)

    def is_temperature_critical(self):
        """Determina si la temperatura está en rango crítico."""
        if self.temperature is None:
            return False
        return self.temperature > 5.0 or self.temperature < -25.0

    def get_temperature_status(self):
        """Retorna el estado de la temperatura."""
        if self.temperature is None:
            return "UNKNOWN"

        if self.temperature > 10.0 or self.temperature < -30.0:
            return "INVALID"  # Fuera del rango permitido
        elif self.temperature > 5.0:
            return "HIGH"  # Alta pero válida
        elif self.temperature < -25.0:
            return "VERY_LOW"  # Muy baja pero válida
        elif self.temperature >= -5.0 and self.temperature <= 3.0:
            return "OPTIMAL"  # Rango óptimo para neveras
        else:
            return "NORMAL"  # Rango normal

    @classmethod
    def get_critical_temperatures(cls, refrigerator=None, days=7):
        """Obtiene registros con temperaturas críticas de los últimos días."""
        from django.utils import timezone
        from datetime import timedelta

        queryset = cls.objects.all()
        if refrigerator:
            queryset = queryset.filter(refrigerator=refrigerator)

        # Filtrar por días recientes
        since_date = timezone.now().date() - timedelta(days=days)
        queryset = queryset.filter(date__gte=since_date)

        # Filtrar temperaturas críticas
        return queryset.filter(
            models.Q(temperature__gt=5.0) | models.Q(temperature__lt=-25.0)
        )

    def __str__(self):
        period_display = dict(self.Period.choices).get(self.period, self.period)
        status = self.get_temperature_status()
        return f"{self.refrigerator} - {self.date} ({period_display}): {self.temperature}°C [{status}]"
