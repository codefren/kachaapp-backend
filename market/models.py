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
