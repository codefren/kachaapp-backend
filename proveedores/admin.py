from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import Provider, Product, ProductBarcode, PurchaseOrder, PurchaseOrderItem


@admin.register(Provider)
class ProviderAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "order_deadline_time", "get_weekdays_display")
    search_fields = ("name",)
    ordering = ("name",)
    fields = ("name", "order_deadline_time", "order_available_weekdays")

    def get_weekdays_display(self, obj):
        """Muestra los días de la semana de forma legible."""
        if not obj.order_available_weekdays:
            return "Sin días configurados"

        weekday_names = {
            0: 'Lun', 1: 'Mar', 2: 'Mié', 3: 'Jue',
            4: 'Vie', 5: 'Sáb', 6: 'Dom'
        }

        days = [weekday_names.get(day, str(day)) for day in obj.order_available_weekdays]
        return ", ".join(days)

    get_weekdays_display.short_description = "Días disponibles"


class ProductBarcodeInline(admin.TabularInline):
    model = ProductBarcode
    extra = 1
    fields = ("code", "type", "is_primary", "notes")
    show_change_link = True
    classes = ("collapse",)


class HasBarcodeFilter(admin.SimpleListFilter):
    title = "Has barcode"
    parameter_name = "has_barcode"

    def lookups(self, request, model_admin):
        return (
            ("yes", "Yes"),
            ("no", "No"),
        )

    def queryset(self, request, queryset):
        value = self.value()
        if value == "yes":
            return queryset.filter(barcodes__isnull=False).distinct()
        if value == "no":
            return queryset.filter(barcodes__isnull=True)
        return queryset


class HasPrimaryBarcodeFilter(admin.SimpleListFilter):
    title = "Has primary barcode"
    parameter_name = "has_primary_barcode"

    def lookups(self, request, model_admin):
        return (
            ("yes", "Yes"),
            ("no", "No"),
        )

    def queryset(self, request, queryset):
        value = self.value()
        if value == "yes":
            return queryset.filter(barcodes__is_primary=True).distinct()
        if value == "no":
            return queryset.exclude(barcodes__is_primary=True).distinct()
        return queryset


@admin.register(Product)
class ProductAdmin(SimpleHistoryAdmin):
    list_display = ("id", "name", "sku", "units_per_box", "amount_boxes")
    search_fields = ("name", "sku", "providers__name", "barcodes__code")
    list_filter = ("providers", HasBarcodeFilter, HasPrimaryBarcodeFilter)
    ordering = ("name",)
    filter_horizontal = ("providers",)
    inlines = [ProductBarcodeInline]

    readonly_fields = ("image_preview",)
    fields = (
        "name",
        "sku",
        "providers",
        "units_per_box",
        "amount_boxes",
        "image",
        "image_preview",
    )

    def image_preview(self, obj):
        if obj and obj.image:
            return f'<img src="{obj.image.url}" style="max-height: 100px;" />'
        return ""
    image_preview.short_description = "Preview"
    image_preview.allow_tags = True


@admin.register(ProductBarcode)
class ProductBarcodeAdmin(admin.ModelAdmin):
    list_display = ("id", "code", "type", "is_primary", "product")
    search_fields = ("code", "product__name", "product__sku")
    list_filter = ("type", "is_primary")
    autocomplete_fields = ("product",)
    ordering = ("code",)


class PurchaseOrderItemInline(admin.TabularInline):
    model = PurchaseOrderItem
    extra = 1
    fields = ("product", "quantity_units", "purchase_unit", "notes")
    autocomplete_fields = ("product",)


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(SimpleHistoryAdmin):
    list_display = ("id", "provider", "status", "ordered_by", "created_at")
    list_filter = ("provider", "status", "created_at")
    search_fields = ("provider__name", "ordered_by__username")
    inlines = [PurchaseOrderItemInline]
    autocomplete_fields = ("provider", "ordered_by")
    ordering = ("-created_at",)
    actions = ("mark_as_draft", "mark_as_placed", "mark_as_received", "mark_as_canceled")

    @admin.action(description="Mark selected orders as Draft")
    def mark_as_draft(self, request, queryset):
        updated = queryset.update(status="DRAFT")
        self.message_user(request, f"{updated} orders marked as Draft")

    @admin.action(description="Mark selected orders as Placed")
    def mark_as_placed(self, request, queryset):
        updated = queryset.update(status="PLACED")
        self.message_user(request, f"{updated} orders marked as Placed")

    @admin.action(description="Mark selected orders as Received")
    def mark_as_received(self, request, queryset):
        updated = queryset.update(status="RECEIVED")
        self.message_user(request, f"{updated} orders marked as Received")

    @admin.action(description="Mark selected orders as Canceled")
    def mark_as_canceled(self, request, queryset):
        updated = queryset.update(status="CANCELED")
        self.message_user(request, f"{updated} orders marked as Canceled")


@admin.register(PurchaseOrderItem)
class PurchaseOrderItemAdmin(admin.ModelAdmin):
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

