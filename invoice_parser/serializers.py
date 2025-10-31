"""Serializers for invoice parser."""

from rest_framework import serializers
from .models import InvoiceParse, InvoiceLineItem


class InvoiceLineItemSerializer(serializers.ModelSerializer):
    """Serializer para líneas de factura."""
    
    class Meta:
        model = InvoiceLineItem
        fields = [
            "id",
            "line_number",
            "codigo",
            "cajas",
            "uc",
            "articulo",
            "udes",
            "unidad",
            "contenedor",
            "created_at",
        ]


class InvoiceParseSerializer(serializers.ModelSerializer):
    """Serializer completo para facturas parseadas."""
    
    lines = InvoiceLineItemSerializer(many=True, read_only=True)
    line_count = serializers.IntegerField(read_only=True)
    
    class Meta:
        model = InvoiceParse
        fields = [
            "id",
            "original_filename",
            "status",
            "csv_data",
            "error_message",
            "created_at",
            "updated_at",
            "completed_at",
            "line_count",
            "lines",
        ]


class InvoiceParseListSerializer(serializers.ModelSerializer):
    """Serializer para listado de facturas parseadas."""
    
    line_count = serializers.IntegerField(read_only=True)
    
    class Meta:
        model = InvoiceParse
        fields = [
            "id",
            "original_filename",
            "status",
            "created_at",
            "completed_at",
            "line_count",
        ]


class InvoiceUploadSerializer(serializers.Serializer):
    """Serializer para subir archivo PDF."""
    
    file = serializers.FileField(
        help_text="Archivo PDF de la factura a parsear"
    )
    expected_lines = serializers.IntegerField(
        default=118,
        help_text="Número esperado de líneas de productos"
    )


class InvoiceParseResponseSerializer(serializers.ModelSerializer):
    """Serializer para respuesta de parseo."""
    
    line_count = serializers.IntegerField(read_only=True)
    
    class Meta:
        model = InvoiceParse
        fields = [
            "id",
            "original_filename",
            "status",
            "line_count",
            "created_at",
        ]
