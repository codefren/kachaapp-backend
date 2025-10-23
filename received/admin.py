"""Admin configuration for received products."""

from django.contrib import admin
from .models import ReceivedProduct, Reception


class ReceivedProductInline(admin.TabularInline):
    model = ReceivedProduct
    extra = 0
    fields = (
        "product",
        "barcode_scanned",
        "quantity_received",
        "is_damaged",
        "is_missing",
        "received_by",
        "received_at",
    )
    readonly_fields = ("received_at",)
    autocomplete_fields = ("product", "received_by")


@admin.register(Reception)
class ReceptionAdmin(admin.ModelAdmin):
    """Admin interface for Reception batches."""

    list_display = (
        "id",
        "purchase_order",
        "market",
        "status",
        "received_by",
        "created_at",
        "invoice_date",
        "invoice_total",
    )
    list_filter = (
        "status",
        "market",
        "created_at",
        "invoice_date",
    )
    search_fields = (
        "id",
        "purchase_order__id",
        "market__name",
        "received_by__username",
    )
    readonly_fields = ("created_at",)
    date_hierarchy = "created_at"
    inlines = [ReceivedProductInline]

    fieldsets = (
        ("Reception Info", {
            "fields": ("purchase_order", "market", "status", "received_by", "created_at"),
        }),
        ("Invoice", {
            "fields": ("invoice_image", "invoice_date", "invoice_time", "invoice_total"),
        }),
    )


@admin.register(ReceivedProduct)
class ReceivedProductAdmin(admin.ModelAdmin):
    """Admin interface for ReceivedProduct."""

    list_display = (
        "id",
        "product",
        "purchase_order",
        "market",
        "reception",
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
        "market",
    )
    search_fields = (
        "product__name",
        "product__sku",
        "barcode_scanned",
        "purchase_order__id",
        "market__name",
        "reception__id",
    )
    readonly_fields = ("received_at",)
    autocomplete_fields = ("product", "purchase_order", "received_by", "market", "reception")
    date_hierarchy = "received_at"
    
    fieldsets = (
        ("Product Information", {
            "fields": ("product", "barcode_scanned", "quantity_received"),
        }),
        ("Purchase Order", {
            "fields": ("purchase_order", "market", "reception"),
        }),
        ("Reception Details", {
            "fields": ("received_by", "received_at", "notes"),
        }),
        ("Status Flags", {
            "fields": ("is_damaged", "is_missing"),
        }),
    )
