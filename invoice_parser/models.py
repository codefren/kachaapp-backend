"""Models for invoice parser."""

from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _


class InvoiceParse(models.Model):
    """Modelo para almacenar información de facturas parseadas."""
    
    class Status(models.TextChoices):
        """Estados del procesamiento de la factura."""
        PENDING = "PENDING", _("Pendiente")
        PROCESSING = "PROCESSING", _("Procesando")
        COMPLETED = "COMPLETED", _("Completado")
        FAILED = "FAILED", _("Fallido")
    
    # Información general
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="invoice_parses",
        verbose_name=_("Subido por")
    )
    original_filename = models.CharField(
        max_length=255,
        verbose_name=_("Nombre del archivo original")
    )
    file = models.FileField(
        upload_to="invoices/%Y/%m/%d/",
        verbose_name=_("Archivo PDF"),
        help_text=_("Archivo PDF de la factura")
    )
    
    # Estado del procesamiento
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name=_("Estado")
    )
    
    # Datos extraídos
    csv_data = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("Datos CSV extraídos"),
        help_text=_("CSV completo extraído del PDF")
    )
    
    # Metadatos de OpenAI
    openai_file_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name=_("ID de archivo en OpenAI")
    )
    openai_response = models.JSONField(
        blank=True,
        null=True,
        verbose_name=_("Respuesta de OpenAI"),
        help_text=_("Respuesta completa de la API de OpenAI")
    )
    
    # Información de error
    error_message = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("Mensaje de error")
    )
    
    # Timestamps
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Creado en")
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Actualizado en")
    )
    completed_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name=_("Completado en")
    )
    
    class Meta:
        verbose_name = _("Factura Parseada")
        verbose_name_plural = _("Facturas Parseadas")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["-created_at"]),
            models.Index(fields=["uploaded_by", "-created_at"]),
            models.Index(fields=["status"]),
        ]
    
    def __str__(self):
        return f"{self.original_filename} - {self.status} ({self.created_at.strftime('%Y-%m-%d %H:%M')})"
    
    @property
    def line_count(self):
        """Retorna el número de líneas extraídas."""
        return self.lines.count()


class InvoiceLineItem(models.Model):
    """Modelo para almacenar líneas individuales de facturas parseadas."""
    
    # Relación con la factura
    invoice_parse = models.ForeignKey(
        InvoiceParse,
        on_delete=models.CASCADE,
        related_name="lines",
        verbose_name=_("Factura")
    )
    
    # Orden de la línea en la factura
    line_number = models.PositiveIntegerField(
        verbose_name=_("Número de línea"),
        help_text=_("Orden de la línea en el CSV")
    )
    
    # Datos de la línea según el formato CSV
    codigo = models.CharField(
        max_length=50,
        blank=True,
        verbose_name=_("Código")
    )
    cajas = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        verbose_name=_("Cajas")
    )
    uc = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        verbose_name=_("UC (Unidades por caja)")
    )
    iva = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        blank=True,
        null=True,
        verbose_name=_("IVA (%)")
    )
    articulo = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("Artículo")
    )
    udes = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        verbose_name=_("Unidades")
    )
    unidad = models.CharField(
        max_length=20,
        blank=True,
        verbose_name=_("Unidad")
    )
    precio = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        verbose_name=_("Precio sin IVA")
    )
    precio_iva = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        verbose_name=_("Precio con IVA")
    )
    importe = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        verbose_name=_("Importe total")
    )
    contenedor = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_("Contenedor")
    )
    
    # Datos sin procesar
    raw_data = models.JSONField(
        blank=True,
        null=True,
        verbose_name=_("Datos sin procesar"),
        help_text=_("Datos originales de la línea del CSV")
    )
    
    # Timestamps
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Creado en")
    )
    
    class Meta:
        verbose_name = _("Línea de Factura")
        verbose_name_plural = _("Líneas de Factura")
        ordering = ["invoice_parse", "line_number"]
        indexes = [
            models.Index(fields=["invoice_parse", "line_number"]),
            models.Index(fields=["codigo"]),
            models.Index(fields=["articulo"]),
        ]
        unique_together = [["invoice_parse", "line_number"]]
    
    def __str__(self):
        return f"Línea {self.line_number}: {self.articulo or self.codigo}"
