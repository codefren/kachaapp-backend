"""Models for purchase orders."""

from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from simple_history.models import HistoricalRecords


class PurchaseOrder(models.Model):
    """Purchase order header for products from providers."""

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PLACED = "PLACED", "Placed"
        RECEIVED = "RECEIVED", "Received"
        SHIPPED = "SHIPPED", "Shipped"
        CANCELED = "CANCELED", "Canceled"

    provider = models.ForeignKey(
        "proveedores.Provider", on_delete=models.PROTECT, related_name="purchase_orders"
    )
    market = models.ForeignKey(
        "market.Market",
        on_delete=models.PROTECT,
        related_name="purchase_orders",
        null=True,
        blank=True,
        db_index=True,
    )
    ordered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="purchase_orders"
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT, db_index=True)
    notes = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Purchase order"
        verbose_name_plural = "Purchase orders"
        indexes = [
            models.Index(fields=["provider", "status"], name="idx_po_provider_status"),
            models.Index(fields=["created_at"], name="idx_po_created_at"),
            models.Index(fields=["market"], name="idx_po_market"),
        ]

    def __str__(self):
        return f"PO #{self.pk or '—'} - {self.provider.name} ({self.status})"


class PurchaseOrderItem(models.Model):
    """Line items for purchase orders."""

    order = models.ForeignKey(
        PurchaseOrder, on_delete=models.CASCADE, related_name="items"
    )
    product = models.ForeignKey(
        "proveedores.Product", on_delete=models.PROTECT, related_name="purchase_order_items"
    )
    quantity_units = models.PositiveIntegerField(default=0, help_text="Units to order")
    
    class PurchaseUnit(models.TextChoices):
        BOXES = "boxes", "boxes"

    purchase_unit = models.CharField(
        max_length=10,
        choices=PurchaseUnit.choices,
        default=PurchaseUnit.BOXES,
        db_index=True,
        help_text="Unit expressed by the purchaser (boxes only)",
    )
    notes = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Purchase order item"
        verbose_name_plural = "Purchase order items"
        indexes = [
            models.Index(fields=["order"], name="idx_poi_order"),
            models.Index(fields=["product"], name="idx_poi_product"),
            models.Index(fields=["order", "product"], name="idx_poi_order_product"),
        ]
        constraints = [
            # quantity_units > 0
            models.CheckConstraint(
                check=models.Q(quantity_units__gt=0), name="chk_poi_qty_gt_0"
            ),
            # Evitar duplicados del mismo producto y misma unidad de compra en la misma orden
            models.UniqueConstraint(
                fields=["order", "product", "purchase_unit"], name="uq_poi_order_product_purchase_unit"
            ),
        ]

    def __str__(self):
        return f"{self.product.name} x {self.quantity_units}"

    def clean(self):
        """Validaciones de negocio adicionales."""
        if self.order and self.order.status == PurchaseOrder.Status.RECEIVED:
            # No permitir crear o modificar ítems si la orden está recibida
            raise ValidationError(
                {"order": "La orden está en estado RECEIVED. No se pueden crear ni modificar ítems."}
            )
        super().clean()

    def save(self, *args, **kwargs):
        """Ejecutar validaciones antes de guardar."""
        # Ejecutar validaciones (incluye clean() y constraints a nivel de modelo)
        self.full_clean()
        # Si el objeto ya existe, asegurar que su orden no esté RECEIVED
        if self.pk:
            original = PurchaseOrderItem.objects.filter(pk=self.pk).select_related("order").first()
            if original and original.order and original.order.status == PurchaseOrder.Status.RECEIVED:
                raise ValidationError("No se pueden modificar ítems de una orden en estado RECEIVED.")
        return super().save(*args, **kwargs)

    def delete(self, using=None, keep_parents=False):
        """Bloquear eliminación si la orden está recibida."""
        if self.order and self.order.status == PurchaseOrder.Status.RECEIVED:
            raise ValidationError("No se pueden eliminar ítems de una orden en estado RECEIVED.")
        return super().delete(using=using, keep_parents=keep_parents)
