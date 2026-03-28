from django.db import models


class Client(models.Model):
    TYPE_CHOICES = [
        ("restaurant", "Restaurante"),
        ("bar", "Bar"),
        ("hotel", "Hotel"),
        ("other", "Otro"),
    ]

    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=20)
    address = models.TextField()

    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    client_type = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        default="other",
    )

    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name
