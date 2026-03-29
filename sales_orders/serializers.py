from rest_framework import serializers
from .models import CustomerOrder, CustomerOrderItem, DeliveryRoute


class DeliveryRouteSerializer(serializers.ModelSerializer):
    orders_count = serializers.SerializerMethodField()
    total_packages = serializers.SerializerMethodField()

    class Meta:
        model = DeliveryRoute
        fields = [
            "id",
            "name",
            "date",
            "driver_name",
            "max_packages",
            "is_active",
            "created_at",
            "orders_count",
            "total_packages",
        ]

    def get_orders_count(self, obj):
        return obj.orders.count()

    def get_total_packages(self, obj):
        return sum(order.delivery_packages for order in obj.orders.all())


class CustomerOrderItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = CustomerOrderItem
        fields = [
            "id",
            "product",
            "product_name",
            "quantity",
            "created_at",
        ]


class CustomerOrderSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source="client.name", read_only=True)
    items = CustomerOrderItemSerializer(many=True, read_only=True)
    route_name = serializers.CharField(source="route.name", read_only=True)

    class Meta:
        model = CustomerOrder
        fields = [
            "id",
            "client",
            "client_name",
            "status",
            "fulfillment_type",
            "requires_preparation",
            "delivery_required",
            "delivery_address",
            "delivery_notes",
            "delivery_zone",
            "delivery_time_from",
            "delivery_time_to",
            "delivery_packages",
            "route",
            "route_name",
            "notes",
            "scheduled_for",
            "created_at",
            "updated_at",
            "items",
            "received_by_name",
            "delivered_at",
            "not_delivered_reason",
            "not_delivered_at",
            "delivery_driver_name",
            "delivery_signature",
            "delivery_photo",
        ]
