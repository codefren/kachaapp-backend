from django.db import models


class Provider(models.Model):
    """Proveedor de productos."""

    name = models.CharField(max_length=150, unique=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Provider"
        verbose_name_plural = "Providers"

    def __str__(self):
        return self.name


class Product(models.Model):
    """Producto suministrado por uno o varios proveedores."""

    name = models.CharField(max_length=150)
    sku = models.CharField(max_length=50, unique=True)
    providers = models.ManyToManyField(Provider, related_name="products")

    class Meta:
        ordering = ["name"]
        verbose_name = "Product"
        verbose_name_plural = "Products"

    def __str__(self):
        return f"{self.sku} - {self.name}"
