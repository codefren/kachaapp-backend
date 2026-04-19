"""Models for purchase orders."""

from datetime import timedelta

from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from simple_history.models import HistoricalRecords


class PurchaseOrder(models.Model):
    """Purchase order header for products from providers."""

    LOCK_TIMEOUT_MINUTES = 10

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PLACED = "PLACED", "Placed"
        IN_PROCESS = "IN_PROCESS", "In process"
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
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="purchase_orders",
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT, db_index=True)
    notes = models.CharField(max_length=300, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    sent_to_email = models.EmailField(blank=True, default="")
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sent_purchase_orders",
    )

    # Locking
    locked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="locked_purchase_orders",
    )
    locked_at = models.DateTimeField(null=True, blank=True)

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
            models.Index(fields=["locked_at"], name="idx_po_locked_at"),
        ]

    def __str__(self):
        return f"PO #{self.pk or '—'} - {self.provider.name} ({self.status})"

    @property
    def lock_expires_at(self):
        if not self.locked_at:
            return None
        return self.locked_at + timedelta(minutes=self.LOCK_TIMEOUT_MINUTES)

    @property
    def is_locked(self):
        if not self.locked_by or not self.locked_at:
            return False
        return timezone.now() < self.lock_expires_at

    def clear_expired_lock(self, save=True):
        if self.locked_by and self.locked_at and not self.is_locked:
            self.locked_by = None
            self.locked_at = None
            if save:
                self.save(update_fields=["locked_by", "locked_at", "updated_at"])

    def can_be_locked_by(self, user):
        self.clear_expired_lock(save=False)
        return not self.locked_by or self.locked_by_id == user.id

    def lock(self, user):
        self.clear_expired_lock(save=False)
        if self.locked_by and self.locked_by_id != user.id:
            raise ValidationError("Este pedido está siendo editado por otro usuario.")
        self.locked_by = user
        self.locked_at = timezone.now()
        self.save(update_fields=["locked_by", "locked_at", "updated_at"])

    def unlock(self, user=None, force=False):
        self.clear_expired_lock(save=False)
        if not self.locked_by:
            return
        if force or user is None or self.locked_by_id == user.id:
            self.locked_by = None
            self.locked_at = None
            self.save(update_fields=["locked_by", "locked_at", "updated_at"])


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
            models.CheckConstraint(
                check=models.Q(quantity_units__gt=0), name="chk_poi_qty_gt_0"
            ),
            models.UniqueConstraint(
                fields=["order", "product", "purchase_unit"], name="uq_poi_order_product_purchase_unit"
            ),
        ]

    def __str__(self):
        return f"{self.product.name} x {self.quantity_units}"

    def clean(self):
        """Validaciones de negocio adicionales."""
        if self.order:
            self.order.clear_expired_lock(save=False)

        if self.order and self.order.status == PurchaseOrder.Status.RECEIVED:
            raise ValidationError(
                {"order": "La orden está en estado RECEIVED. No se pueden crear ni modificar ítems."}
            )
        super().clean()

    def save(self, *args, **kwargs):
        """Ejecutar validaciones antes de guardar."""
        self.full_clean()
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
