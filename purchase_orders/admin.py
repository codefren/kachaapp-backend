"""Admin configuration for purchase orders."""

from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import PurchaseOrder, PurchaseOrderItem


class PurchaseOrderItemInline(admin.TabularInline):
    """Inline admin for purchase order items."""
    
    model = PurchaseOrderItem
    extra = 1
    fields = ("product", "quantity_units", "purchase_unit", "notes")
    autocomplete_fields = ("product",)


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(SimpleHistoryAdmin):
    """Admin configuration for PurchaseOrder model."""
    
    list_display = ("id", "provider", "status", "ordered_by", "created_at")
    list_filter = ("provider", "status", "created_at")
    search_fields = ("provider__name", "ordered_by__username")
    inlines = [PurchaseOrderItemInline]
    autocomplete_fields = ("provider", "ordered_by")
    ordering = ("-created_at",)
    actions = ("mark_as_draft", "mark_as_placed", "mark_as_received", "mark_as_canceled")

    @admin.action(description="Mark selected orders as Draft")
    def mark_as_draft(self, request, queryset):
        """Mark selected orders as Draft."""
        updated = queryset.update(status="DRAFT")
        self.message_user(request, f"{updated} orders marked as Draft")

    @admin.action(description="Mark selected orders as Placed")
    def mark_as_placed(self, request, queryset):
        """Mark selected orders as Placed."""
        updated = queryset.update(status="PLACED")
        self.message_user(request, f"{updated} orders marked as Placed")

    @admin.action(description="Mark selected orders as Received")
    def mark_as_received(self, request, queryset):
        """Mark selected orders as Received."""
        updated = queryset.update(status="RECEIVED")
        self.message_user(request, f"{updated} orders marked as Received")

    @admin.action(description="Mark selected orders as Canceled")
    def mark_as_canceled(self, request, queryset):
        """Mark selected orders as Canceled."""
        updated = queryset.update(status="CANCELED")
        self.message_user(request, f"{updated} orders marked as Canceled")


@admin.register(PurchaseOrderItem)
class PurchaseOrderItemAdmin(admin.ModelAdmin):
    """Admin configuration for PurchaseOrderItem model."""
    
    list_display = (
        "id",
        "order",
        "product",
        "quantity_units",
        "purchase_unit",
        "created_at",
    )
    list_filter = ("order", "product", "created_at")
    search_fields = (
        "product__name",
        "product__sku",
        "order__provider__name",
        "order__ordered_by__username",
    )
    autocomplete_fields = ("order", "product")
    ordering = ("-created_at",)
    list_select_related = ("order", "product")
