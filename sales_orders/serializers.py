from rest_framework import serializers

from .models import CustomerOrder, CustomerOrderItem


class CustomerOrderItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = CustomerOrderItem
        fields = [
            "id",
            "order",
            "product",
            "product_name",
            "quantity",
            "created_at",
        ]
        read_only_fields = ["id", "created_at", "product_name"]


class CustomerOrderSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source="client.name", read_only=True)
    created_by_username = serializers.CharField(source="created_by.username", read_only=True)
    items = CustomerOrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = CustomerOrder
        fields = [
            "id",
            "client",
            "client_name",
            "created_by",
            "created_by_username",
            "status",
            "notes",
            "items",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "created_by",
            "created_at",
            "updated_at",
            "client_name",
            "created_by_username",
            "items",
        ]
