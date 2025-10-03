"""Admin configuration for received products."""

from django.contrib import admin
from .models import ReceivedProduct


@admin.register(ReceivedProduct)
class ReceivedProductAdmin(admin.ModelAdmin):
    """Admin interface for ReceivedProduct."""

    list_display = (
        "id",
        "product",
        "purchase_order",
        "barcode_scanned",
        "quantity_received",
        "received_by",
        "received_at",
        "is_damaged",
        "is_missing",
    )
    list_filter = (
        "is_damaged",
        "is_missing",
        "received_at",
        "purchase_order__provider",
    )
    search_fields = (
        "product__name",
        "product__sku",
        "barcode_scanned",
        "purchase_order__id",
    )
    readonly_fields = ("received_at",)
    autocomplete_fields = ("product", "purchase_order", "received_by")
    date_hierarchy = "received_at"
    
    fieldsets = (
        ("Product Information", {
            "fields": ("product", "barcode_scanned", "quantity_received"),
        }),
        ("Purchase Order", {
            "fields": ("purchase_order",),
        }),
        ("Reception Details", {
            "fields": ("received_by", "received_at", "notes"),
        }),
        ("Status Flags", {
            "fields": ("is_damaged", "is_missing"),
        }),
    )
