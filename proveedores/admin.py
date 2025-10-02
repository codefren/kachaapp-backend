from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import Provider, Product, ProductBarcode


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

