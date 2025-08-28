from rest_framework import serializers

from .models import (
    PurchaseOrder,
    PurchaseOrderItem,
    Product,
    Provider,
    ProductBarcode,
)


class PurchaseOrderItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    subtotal = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = PurchaseOrderItem
        fields = (
            "id",
            "product",
            "product_name",
            "quantity_units",
            "unit_price",
            "subtotal",
            "notes",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "subtotal", "created_at", "updated_at")


class ProviderSerializer(serializers.ModelSerializer):
    products_count = serializers.IntegerField(source="products.count", read_only=True)

    class Meta:
        model = Provider
        fields = (
            "id",
            "name",
            "created_at",
            "updated_at",
            "products_count",
        )


class ProductBarcodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductBarcode
        fields = ("id", "code", "type", "is_primary")


class ProviderMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Provider
        fields = ("id", "name")


class ProductSerializer(serializers.ModelSerializer):
    providers = ProviderMiniSerializer(many=True, read_only=True)
    barcodes = ProductBarcodeSerializer(many=True, read_only=True)
    current_user_favorite = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = (
            "id",
            "name",
            "sku",
            "stock_units",
            "units_per_box",
            "is_favorite",
            "image",
            "providers",
            "barcodes",
            "current_user_favorite",
            "created_at",
            "updated_at",
        )

    def get_current_user_favorite(self, obj):
        request = self.context.get("request")
        if request is None or request.user.is_anonymous:
            return False
        try:
            return obj.favorites.filter(user_id=request.user.id).exists()
        except Exception:
            return False

    def get_image(self, obj):
        image_field = getattr(obj, "image", None)
        if not image_field:
            return None
        try:
            url = image_field.url
        except Exception:
            return None
        request = self.context.get("request")
        if request is not None:
            abs_url = request.build_absolute_uri(url)
        else:
            abs_url = url
        if abs_url.startswith("http://"):
            abs_url = "https://" + abs_url[len("http://"):]
        return abs_url


class PurchaseOrderSerializer(serializers.ModelSerializer):
    provider_name = serializers.CharField(source="provider.name", read_only=True)
    ordered_by_username = serializers.CharField(source="ordered_by.username", read_only=True)
    items = PurchaseOrderItemSerializer(many=True)

    class Meta:
        model = PurchaseOrder
        fields = (
            "id",
            "provider",
            "provider_name",
            "ordered_by",
            "ordered_by_username",
            "status",
            "notes",
            "items",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def create(self, validated_data):
        items_data = validated_data.pop("items", [])
        order = PurchaseOrder.objects.create(**validated_data)
        for item in items_data:
            PurchaseOrderItem.objects.create(order=order, **item)
        return order

    def update(self, instance, validated_data):
        items_data = validated_data.pop("items", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if items_data is not None:
            # Simple strategy: clear and recreate
            instance.items.all().delete()
            for item in items_data:
                PurchaseOrderItem.objects.create(order=instance, **item)
        return instance
