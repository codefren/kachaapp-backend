from django.db import models
from .utils import haversine_distance

class Market(models.Model):
    name = models.CharField(max_length=255)
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
