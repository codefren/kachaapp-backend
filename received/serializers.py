"""Serializers for received products."""

from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field

from .models import ReceivedProduct


class ReceivedProductSerializer(serializers.ModelSerializer):
    """Serializer for received products with detailed information."""

    product_name = serializers.CharField(source="product.name", read_only=True)
    product_sku = serializers.CharField(source="product.sku", read_only=True)
    product_image = serializers.SerializerMethodField()
    received_by_username = serializers.CharField(source="received_by.username", read_only=True)
    purchase_order_status = serializers.CharField(source="purchase_order.status", read_only=True)
    provider_name = serializers.CharField(source="purchase_order.provider.name", read_only=True)

    class Meta:
        model = ReceivedProduct
        fields = (
            "id",
            "purchase_order",
            "purchase_order_status",
            "provider_name",
            "product",
            "product_name",
            "product_sku",
            "product_image",
            "barcode_scanned",
            "quantity_received",
            "received_by",
            "received_by_username",
            "received_at",
            "notes",
            "is_damaged",
            "is_missing",
        )
        read_only_fields = ("id", "received_at", "received_by")

    @extend_schema_field({"type": "string", "nullable": True})
    def get_product_image(self, obj):
        """Get absolute HTTPS URL for product image."""
        product = getattr(obj, "product", None)
        if not product:
            return None
        image_field = getattr(product, "image", None)
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

    def create(self, validated_data):
        """Create a received product and auto-assign received_by."""
        request = self.context.get("request")
        if request is not None and not request.user.is_anonymous:
            validated_data["received_by"] = request.user
        return super().create(validated_data)


