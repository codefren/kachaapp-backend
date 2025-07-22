from django.db import models
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
        distancia = haversine_distance(self.latitude, self.longitude, user_lat, user_lon)
        return distancia <= max_distance_meters


class LoginHistory(models.Model):
    LOGIN = 'login'
    REFRESH = 'refresh'
    EVENT_TYPE_CHOICES = [
        (LOGIN, 'Login'),
        (REFRESH, 'Refresh'),
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
    """Registro diario de la temperatura de una nevera."""

    refrigerator = models.ForeignKey(
        Refrigerator,
        related_name="temperature_records",
        on_delete=models.CASCADE,
    )
    date = models.DateField()
    temperature = models.FloatField()
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("refrigerator", "date")
        ordering = ["-date"]
        verbose_name = "Temperature Record"
        verbose_name_plural = "Temperature Records"

    def __str__(self):
        return f"{self.refrigerator} - {self.date} : {self.temperature}°C"
