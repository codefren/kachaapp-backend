from django.db import models
from django.conf import settings


class Provider(models.Model):
    """Proveedor de productos."""

    name = models.CharField(max_length=150, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Provider"
        verbose_name_plural = "Providers"

    def __str__(self):
        return self.name


class ProductFavorite(models.Model):
    """Relación de favoritos entre un usuario y un producto (por usuario)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="product_favorites"
    )
    product = models.ForeignKey(
        'Product', on_delete=models.CASCADE, related_name="favorites"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "product")
        verbose_name = "Product favorite"
        verbose_name_plural = "Product favorites"
        indexes = [
            models.Index(fields=["user", "product"], name="idx_fav_user_product"),
            models.Index(fields=["product"], name="idx_fav_product"),
        ]

    def __str__(self):
        return f"{self.user} - {self.product}"


class Product(models.Model):
    """Producto suministrado por uno o varios proveedores."""

    name = models.CharField(max_length=150)
    sku = models.CharField(max_length=50, unique=True)
    providers = models.ManyToManyField(Provider, related_name="products")
    stock_units = models.PositiveIntegerField(
        default=0, help_text="Units in stock (retail)"
    )
    units_per_box = models.PositiveIntegerField(
        default=1, help_text="Units per box (wholesale)"
    )
    is_favorite = models.BooleanField(default=False)
    image = models.ImageField(upload_to="products/", blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Product"
        verbose_name_plural = "Products"

    def __str__(self):
        return self.name


class ProductBarcode(models.Model):
    """Códigos de barras asociados a un producto.

    Usar un modelo separado permite almacenar múltiples códigos por producto
    (por ejemplo: unidad, caja, master), distintos tipos (EAN-13, UPC-A, QR),
    y marcar uno como principal para búsquedas rápidas.
    """

    class BarcodeType(models.TextChoices):
        EAN13 = "EAN13", "EAN-13"
        EAN8 = "EAN8", "EAN-8"
        UPC_A = "UPC_A", "UPC-A"
        CODE128 = "CODE128", "Code 128"
        QR = "QR", "QR"
        OTHER = "OTHER", "Other"

    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="barcodes"
    )
    code = models.CharField(max_length=32, unique=True, db_index=True)
    type = models.CharField(
        max_length=16, choices=BarcodeType.choices, default=BarcodeType.EAN13
    )
    is_primary = models.BooleanField(default=False)
    notes = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["product_id", "-is_primary", "code"]
        verbose_name = "Product barcode"
        verbose_name_plural = "Product barcodes"
        indexes = [
            models.Index(fields=["code"], name="idx_barcode_code"),
            models.Index(fields=["product", "is_primary"], name="idx_barcode_primary"),
        ]

    def __str__(self):
        label = dict(self.BarcodeType.choices).get(self.type, self.type)
        return f"{self.code} ({label})"

    def save(self, *args, **kwargs):
        # Asegurar que solo haya un código principal por producto.
        super().save(*args, **kwargs)
        if self.is_primary:
            ProductBarcode.objects.filter(product=self.product, is_primary=True).exclude(
                pk=self.pk
            ).update(is_primary=False)


class PurchaseOrder(models.Model):
    """Purchase order header for products from providers."""

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PLACED = "PLACED", "Placed"
        RECEIVED = "RECEIVED", "Received"
        CANCELED = "CANCELED", "Canceled"

    provider = models.ForeignKey(
        Provider, on_delete=models.PROTECT, related_name="purchase_orders"
    )
    ordered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="purchase_orders"
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT, db_index=True)
    notes = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Purchase order"
        verbose_name_plural = "Purchase orders"
        indexes = [
            models.Index(fields=["provider", "status"], name="idx_po_provider_status"),
            models.Index(fields=["created_at"], name="idx_po_created_at"),
        ]

    def __str__(self):
        return f"PO #{self.pk or '—'} - {self.provider.name} ({self.status})"


class PurchaseOrderItem(models.Model):
    """Line items for purchase orders."""

    order = models.ForeignKey(
        PurchaseOrder, on_delete=models.CASCADE, related_name="items"
    )
    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name="purchase_order_items"
    )
    quantity_units = models.PositiveIntegerField(default=0, help_text="Units to order")
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    notes = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Purchase order item"
        verbose_name_plural = "Purchase order items"
        indexes = [
            models.Index(fields=["order"], name="idx_poi_order"),
            models.Index(fields=["product"], name="idx_poi_product"),
        ]

    def __str__(self):
        return f"{self.product.name} x {self.quantity_units}"

    @property
    def subtotal(self):
        return self.quantity_units * self.unit_price
