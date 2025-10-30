"""Admin for invoice parser."""

from django.contrib import admin
from .models import InvoiceParse, InvoiceLineItem


class InvoiceLineItemInline(admin.TabularInline):
    """Inline para mostrar líneas de factura en el admin de InvoiceParse."""
    
    model = InvoiceLineItem
    extra = 0
    fields = [
        "line_number",
        "codigo",
        "articulo",
        "cajas",
        "uc",
        "udes",
        "precio",
        "importe",
    ]
    readonly_fields = fields
    can_delete = False
    
    def has_add_permission(self, request, obj=None):
        return False


@admin.register(InvoiceParse)
class InvoiceParseAdmin(admin.ModelAdmin):
    """Admin para facturas parseadas."""
    
    list_display = [
        "id",
        "original_filename",
        "uploaded_by",
        "status",
        "line_count",
        "created_at",
        "completed_at",
    ]
    list_filter = [
        "status",
        "created_at",
        "uploaded_by",
    ]
    search_fields = [
        "original_filename",
        "uploaded_by__username",
        "openai_file_id",
    ]
    readonly_fields = [
        "uploaded_by",
        "original_filename",
        "file",
        "status",
        "csv_data",
        "openai_file_id",
        "openai_response",
        "error_message",
        "created_at",
        "updated_at",
        "completed_at",
        "line_count",
    ]
    fieldsets = [
        (
            "Información General",
            {
                "fields": [
                    "uploaded_by",
                    "original_filename",
                    "file",
                    "status",
                ]
            },
        ),
        (
            "Datos Extraídos",
            {
                "fields": [
                    "csv_data",
                    "line_count",
                ],
                "classes": ["collapse"],
            },
        ),
        (
            "Metadatos de OpenAI",
            {
                "fields": [
                    "openai_file_id",
                    "openai_response",
                ],
                "classes": ["collapse"],
            },
        ),
        (
            "Errores",
            {
                "fields": ["error_message"],
                "classes": ["collapse"],
            },
        ),
        (
            "Fechas",
            {
                "fields": [
                    "created_at",
                    "updated_at",
                    "completed_at",
                ],
            },
        ),
    ]
    inlines = [InvoiceLineItemInline]
    
    def has_add_permission(self, request):
        """No permitir crear facturas desde el admin."""
        return False
    
    def has_delete_permission(self, request, obj=None):
        """Permitir eliminar facturas."""
        return True


@admin.register(InvoiceLineItem)
class InvoiceLineItemAdmin(admin.ModelAdmin):
    """Admin para líneas de factura."""
    
    list_display = [
        "id",
        "invoice_parse",
        "line_number",
        "codigo",
        "articulo",
        "cajas",
        "udes",
        "precio",
        "importe",
    ]
    list_filter = [
        "invoice_parse__status",
        "created_at",
    ]
    search_fields = [
        "codigo",
        "articulo",
        "invoice_parse__original_filename",
    ]
    readonly_fields = [
        "invoice_parse",
        "line_number",
        "codigo",
        "cajas",
        "uc",
        "iva",
        "articulo",
        "udes",
        "unidad",
        "precio",
        "precio_iva",
        "importe",
        "contenedor",
        "raw_data",
        "created_at",
    ]
    fieldsets = [
        (
            "Información General",
            {
                "fields": [
                    "invoice_parse",
                    "line_number",
                ]
            },
        ),
        (
            "Datos del Producto",
            {
                "fields": [
                    "codigo",
                    "articulo",
                    "cajas",
                    "uc",
                    "udes",
                    "unidad",
                    "contenedor",
                ]
            },
        ),
        (
            "Precios e Impuestos",
            {
                "fields": [
                    "precio",
                    "precio_iva",
                    "iva",
                    "importe",
                ]
            },
        ),
        (
            "Datos Sin Procesar",
            {
                "fields": ["raw_data"],
                "classes": ["collapse"],
            },
        ),
        (
            "Fechas",
            {
                "fields": ["created_at"],
            },
        ),
    ]
    
    def has_add_permission(self, request):
        """No permitir crear líneas desde el admin."""
        return False
    
    def has_delete_permission(self, request, obj=None):
        """No permitir eliminar líneas individuales."""
        return False
