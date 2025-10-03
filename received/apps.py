"""App configuration for received."""

from django.apps import AppConfig


class ReceivedConfig(AppConfig):
    """Configuration for the received app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "received"
    verbose_name = "Received Products"
