"""Django app configuration for purchase_orders."""

from django.apps import AppConfig


class PurchaseOrdersConfig(AppConfig):
    """Configuration for the purchase_orders app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "purchase_orders"
    verbose_name = "Purchase Orders"
