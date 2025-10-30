"""Serializers for invoice parser."""

from rest_framework import serializers
from .models import InvoiceParse, InvoiceLineItem


class InvoiceUploadSerializer(serializers.Serializer):
    """Serializer para subir archivos PDF de facturas."""
    
    file = serializers.FileField(
        required=True,
        help_text="Archivo PDF de la factura a procesar"
    )
    
    def validate_file(self, value):
        """Valida que el archivo sea un PDF."""
        if not value.name.lower().endswith('.pdf'):
            raise serializers.ValidationError(
                "El archivo debe ser un PDF (.pdf)"
            )
        
        # Límite de 10MB para el archivo
        if value.size > 10 * 1024 * 1024:
            raise serializers.ValidationError(
                "El archivo no puede superar los 10MB"
            )
        
        return value


class InvoiceParseResponseSerializer(serializers.Serializer):
    """Serializer para la respuesta del parseo de factura."""
    
    csv_data = serializers.CharField(
        help_text="Datos de la factura en formato CSV"
    )
    file_id = serializers.CharField(
        help_text="ID del archivo en OpenAI",
        required=False
    )


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
        read_only_fields = ["id", "created_at"]


class InvoiceParseSerializer(serializers.ModelSerializer):
    """Serializer para facturas parseadas."""
    
    lines = InvoiceLineItemSerializer(many=True, read_only=True)
    uploaded_by_username = serializers.CharField(
        source="uploaded_by.username",
        read_only=True
    )
    line_count = serializers.IntegerField(read_only=True)
    
    class Meta:
        model = InvoiceParse
        fields = [
            "id",
            "uploaded_by",
            "uploaded_by_username",
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
            "lines",
            "line_count",
        ]
        read_only_fields = [
            "id",
            "uploaded_by",
            "status",
            "csv_data",
            "openai_file_id",
            "openai_response",
            "error_message",
            "created_at",
            "updated_at",
            "completed_at",
        ]


class InvoiceParseListSerializer(serializers.ModelSerializer):
    """Serializer simplificado para listar facturas parseadas."""
    
    uploaded_by_username = serializers.CharField(
        source="uploaded_by.username",
        read_only=True
    )
    line_count = serializers.IntegerField(read_only=True)
    
    class Meta:
        model = InvoiceParse
        fields = [
            "id",
            "uploaded_by_username",
            "original_filename",
            "status",
            "line_count",
            "created_at",
            "completed_at",
            "error_message",
        ]
        read_only_fields = fields
