from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field

from purchase_orders.models import PurchaseOrder
from .models import (
    Product,
    Provider,
    ProductBarcode,
)


class ProviderSerializer(serializers.ModelSerializer):
    has_received_orders = serializers.SerializerMethodField()
    order_available_dates = serializers.SerializerMethodField()
    has_draft_reception = serializers.BooleanField(read_only=True)
    draft_reception_order_id = serializers.IntegerField(read_only=True, allow_null=True)

    class Meta:
        model = Provider
        fields = (
            "id",
            "name",
            "order_deadline_time",
            "order_available_weekdays",
            "order_available_dates",
            "has_received_orders",
            "has_draft_reception",
            "draft_reception_order_id",
        )

    @extend_schema_field({
        "type": "object",
        "properties": {
            "status": {"type": "string", "nullable": True},
            "order_id": {"type": "integer", "nullable": True}
        }
    })
    def get_has_received_orders(self, obj):
        """Retorna información de la última orden PLACED o DRAFT del proveedor."""
        from django.db.models import Q
        from purchase_orders.models import PurchaseOrder
        order = PurchaseOrder.objects.filter(
            provider=obj
        ).filter(
            Q(status=PurchaseOrder.Status.PLACED) | Q(status=PurchaseOrder.Status.DRAFT)
        ).order_by('-created_at').first()
        return {
            "status": order.status if order else None,
            "order_id": order.id if order else None
        }

    @extend_schema_field(serializers.ListField(child=serializers.DictField()))
    def get_order_available_dates(self, obj):
        """Retorna las fechas de la próxima semana donde el proveedor acepta pedidos con el nombre del día."""
        from django.utils import timezone
        from datetime import timedelta
        
        if not obj.order_available_weekdays:
            return []
        
        # Nombres de días en español
        weekday_names = {
            0: 'Lunes',
            1: 'Martes', 
            2: 'Miércoles',
            3: 'Jueves',
            4: 'Viernes',
            5: 'Sábado',
            6: 'Domingo'
        }

        today = timezone.now().date()
        dates = []

        # Buscar las próximas fechas en los próximos 7 días
        for i in range(7):
            check_date = today + timedelta(days=i)
            weekday = check_date.weekday()  # 0=Lunes, 6=Domingo

            if weekday in obj.order_available_weekdays:
                day_name = weekday_names[weekday]
                formatted_date = check_date.strftime('%d/%m/%Y')
                dates.append(f"{day_name} {formatted_date}")

        return dates


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
    # Nota: Ya no calculamos amount_boxes desde órdenes; se expone tal cual del modelo.

    class Meta:
        model = Product
        fields = (
            "id",
            "name",
            "sku",
            "units_per_box",
            "image",
            "providers",
            "barcodes",
            "current_user_favorite",
            "amount_boxes",
            "created_at",
            "updated_at",
        )

    @extend_schema_field(serializers.BooleanField())
    def get_current_user_favorite(self, obj):
        request = self.context.get("request")
        if request is None or request.user.is_anonymous:
            return False
        try:
            return obj.favorites.filter(user_id=request.user.id).exists()
        except Exception:
            return False

    @extend_schema_field(serializers.CharField(allow_null=True))
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
