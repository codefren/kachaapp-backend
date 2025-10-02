from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from simple_history.models import HistoricalRecords


class Provider(models.Model):
    """Proveedor de productos."""

    WEEKDAYS = [
        (0, 'Lunes'),
        (1, 'Martes'),
        (2, 'Miércoles'),
        (3, 'Jueves'),
        (4, 'Viernes'),
        (5, 'Sábado'),
        (6, 'Domingo'),
    ]

    name = models.CharField(max_length=150, unique=True)
    # Hora límite para hacer pedidos (formato HH:MM)
    order_deadline_time = models.TimeField(help_text="Hora límite para hacer pedidos (ej: 14:30)")
    # Días de la semana en que acepta pedidos (JSON array de números 0-6)
    order_available_weekdays = models.JSONField(
        default=list,
        blank=True,
        help_text="Días de la semana que acepta pedidos (0=Lunes, 6=Domingo). Ej: [0,1,2,3,4] para Lun-Vie"
    )
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

#imagens/app/kch
# se relacionan por el codigo del articulo
# 

# History of Product and Purchase Order Model




class Product(models.Model):
    """Producto suministrado por uno o varios proveedores."""

    name = models.CharField(max_length=150)
    sku = models.CharField(max_length=50, unique=True)
    providers = models.ManyToManyField(Provider, related_name="products")
    amount_boxes = models.PositiveIntegerField(
        default=0, help_text="Boxes purchased in the last order"
    )
    units_per_box = models.PositiveIntegerField(default=1) # Unidades por caja
    image = models.ImageField(upload_to="products/", blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

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
