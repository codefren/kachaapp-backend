"""Models for received products from purchase orders."""

from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from market.models import Market


class Reception(models.Model):
    """Batch/lote de recepción de productos para una orden en una tienda."""

    purchase_order = models.ForeignKey(
        "purchase_orders.PurchaseOrder",
        on_delete=models.PROTECT,
        related_name="receptions",
    )
    market = models.ForeignKey(
        Market,
        on_delete=models.PROTECT,
        related_name="receptions",
    )
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="receptions",
    )
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        COMPLETED = "COMPLETED", "Completed"

    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.DRAFT,
        help_text="Reception status",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Reception"
        verbose_name_plural = "Receptions"
        indexes = [
            models.Index(
                fields=["purchase_order", "market", "status"],
                name="idx_reception_po_market_status",
            )
        ]

    def __str__(self) -> str:
        return f"Reception #{self.id} - PO {self.purchase_order_id} - Market {self.market_id}"


class ReceivedProduct(models.Model):
    """Tracks individual products received from purchase orders."""

    purchase_order = models.ForeignKey(
        "purchase_orders.PurchaseOrder",
        on_delete=models.PROTECT,
        related_name="received_products",
        help_text="Purchase order this product was received from",
    )
    product = models.ForeignKey(
        "proveedores.Product",
        on_delete=models.PROTECT,
        related_name="received_records",
        help_text="Product that was received",
    )
    market = models.ForeignKey(
        Market,
        on_delete=models.PROTECT,
        related_name="received_products",
        help_text="Market where the product was received",
    )
    reception = models.ForeignKey(
        Reception,
        on_delete=models.CASCADE,
        related_name="items",
        null=True,
        blank=True,
        help_text="Reception batch this record belongs to",
    )
    barcode_scanned = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
        help_text="Barcode that was scanned when receiving this product",
    )
    quantity_received = models.PositiveIntegerField(
        default=1,
        help_text="Quantity of units received",
    )
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="received_products",
        help_text="User who received the product",
    )
    received_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="Date and time when product was received",
    )
    notes = models.CharField(
        max_length=500,
        blank=True,
        help_text="Additional notes about the received product",
    )
    is_damaged = models.BooleanField(
        default=False,
        help_text="Flag if product was received damaged",
    )
    is_missing = models.BooleanField(
        default=False,
        help_text="Flag if product was expected but missing",
    )
    is_over_received = models.BooleanField(
        default=False,
        help_text="Quantity received is greater than ordered for this product",
    )
    is_under_received = models.BooleanField(
        default=False,
        help_text="Quantity received is less than ordered for this product",
    )

    class Meta:
        ordering = ["-received_at"]
        verbose_name = "Received Product"
        verbose_name_plural = "Received Products"
        indexes = [
            models.Index(fields=["purchase_order", "product"], name="idx_rp_po_product"),
            models.Index(fields=["purchase_order", "market"], name="idx_rp_po_market"),
            models.Index(fields=["barcode_scanned"], name="idx_rp_barcode"),
            models.Index(fields=["received_at"], name="idx_rp_received_at"),
            models.Index(fields=["received_by"], name="idx_rp_received_by"),
        ]

    def __str__(self):
        return f"{self.product.name} - PO #{self.purchase_order_id} ({self.quantity_received} units)"

    def clean(self):
        """Validate received product data."""
        if self.quantity_received < 0:
            raise ValidationError({"quantity_received": "Quantity must be greater than or equal to 0."})
        
        # Validate that product belongs to the purchase order
        if self.purchase_order_id and self.product_id:
            from purchase_orders.models import PurchaseOrderItem
            exists = PurchaseOrderItem.objects.filter(
                order_id=self.purchase_order_id,
                product_id=self.product_id,
            ).exists()
            if not exists:
                raise ValidationError({
                    "product": "This product does not belong to the selected purchase order."
                })

    def save(self, *args, **kwargs):
        """Execute validations before saving."""
        self.full_clean()
        return super().save(*args, **kwargs)
