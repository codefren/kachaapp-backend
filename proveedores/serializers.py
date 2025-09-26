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
    # Campo editable independiente (write-only). Para salida, lo calculamos desde product.
    amount_boxes = serializers.IntegerField(required=False, write_only=True)
    product_image = serializers.SerializerMethodField()
    purchase_unit = serializers.ChoiceField(choices=["boxes"], required=False)

    class Meta:
        model = PurchaseOrderItem
        fields = (
            "id",
            "product",
            "amount_boxes",
            "product_name",
            "product_image",
            "quantity_units",
            "purchase_unit",
            "notes",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def get_product_image(self, obj):
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
        # Extraer amount_boxes del payload para aplicarlo al Product asociado
        amount_boxes_val = validated_data.pop("amount_boxes", None)
        obj = super().create(validated_data)
        if amount_boxes_val is not None:
            try:
                Product.objects.filter(pk=obj.product_id).update(amount_boxes=int(amount_boxes_val))
            except Exception:
                pass
        return obj

    def update(self, instance, validated_data):
        amount_boxes_val = validated_data.pop("amount_boxes", None)
        obj = super().update(instance, validated_data)
        if amount_boxes_val is not None:
            try:
                Product.objects.filter(pk=obj.product_id).update(amount_boxes=int(amount_boxes_val))
            except Exception:
                pass
        return obj

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Incluir amount_boxes desde el producto asociado en la salida
        try:
            data["amount_boxes"] = int(getattr(instance.product, "amount_boxes", 0) or 0)
        except Exception:
            data["amount_boxes"] = 0
        return data


class ProviderSerializer(serializers.ModelSerializer):
    products_count = serializers.IntegerField(source="products.count", read_only=True)
    has_received_orders = serializers.SerializerMethodField()
    order_available_dates = serializers.SerializerMethodField()

    class Meta:
        model = Provider
        fields = (
            "id",
            "name",
            "order_deadline_time",
            "order_available_weekdays",
            "order_available_dates",
            "created_at",
            "updated_at",
            "products_count",
            "has_received_orders",
        )

    def get_has_received_orders(self, obj):
        """Retorna el estado de la orden si el proveedor tiene órdenes en estado DRAFT o PLACED."""
        from .models import PurchaseOrder
        order = PurchaseOrder.objects.filter(
            provider=obj,
            status__in=[PurchaseOrder.Status.DRAFT, PurchaseOrder.Status.PLACED]
        ).first()
        return {"status": order.status if order else None,
                "order_id": order.id if order else None}

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
        read_only_fields = ("id", "created_at", "updated_at", "ordered_by")

    def create(self, validated_data):
        items_data = validated_data.pop("items", [])
        # Forzar el creador de la orden desde el request
        request = self.context.get("request")
        if request is not None and not request.user.is_anonymous:
            validated_data["ordered_by"] = request.user
        order = PurchaseOrder.objects.create(**validated_data)
        # Consolidar por (product_id, purchase_unit="boxes") para respetar la restricción de unicidad
        consolidated: dict[tuple[int, str], dict] = {}
        boxes_override_by_product: dict[int, int] = {}
        for item in items_data:
            normalized = self._normalize_item(item)
            # Leer override antes de limpiar
            amt_raw = (item or {}).get("amount_boxes")
            # 'amount_boxes' NO es campo del modelo PurchaseOrderItem; quitarlo antes de crear
            normalized.pop("amount_boxes", None)
            product_ref = normalized.get("product")
            try:
                product_id = product_ref.pk if isinstance(product_ref, Product) else int(product_ref)
            except Exception:
                # Si no se puede resolver, crear directo y seguir
                PurchaseOrderItem.objects.create(order=order, **normalized)
                continue
            key = (product_id, "boxes")
            entry = consolidated.setdefault(key, {"quantity_units": 0, "purchase_unit": "boxes"})
            entry["quantity_units"] += int(normalized.get("quantity_units", 0) or 0)
            if "notes" in normalized:
                entry["notes"] = normalized["notes"]
            # Registrar último override por producto si vino
            if amt_raw is not None:
                try:
                    boxes_override_by_product[product_id] = int(amt_raw)
                except (TypeError, ValueError):
                    pass
        for (pid, _pu), data in consolidated.items():
            PurchaseOrderItem.objects.create(order=order, product_id=pid, **data)
        # Persistir en Product.amount_boxes si vino amount_boxes en el payload
        for pid, final_boxes in boxes_override_by_product.items():
            try:
                Product.objects.filter(pk=pid).update(amount_boxes=int(final_boxes))
            except Exception:
                pass
        return order

    def update(self, instance, validated_data):
        items_data = validated_data.pop("items", None)
        validated_data.pop("ordered_by", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if items_data is not None:
            # Borrar todos los ítems y recrear consolidando por producto para respetar unicidad
            instance.items.all().delete()
            consolidated: dict[tuple[int, str], dict] = {}
            boxes_override_by_product: dict[int, int] = {}
            for item in items_data:
                normalized = self._normalize_item(item)
                amt_raw = (item or {}).get("amount_boxes")
                normalized.pop("amount_boxes", None)
                product_ref = normalized.get("product")
                try:
                    product_id = product_ref.pk if isinstance(product_ref, Product) else int(product_ref)
                except Exception:
                    PurchaseOrderItem.objects.create(order=instance, **normalized)
                    continue
                key = (product_id, "boxes")
                entry = consolidated.setdefault(key, {"quantity_units": 0, "purchase_unit": "boxes"})
                entry["quantity_units"] += int(normalized.get("quantity_units", 0) or 0)
                if "notes" in normalized:
                    entry["notes"] = normalized["notes"]
                if amt_raw is not None:
                    try:
                        boxes_override_by_product[product_id] = int(amt_raw)
                    except (TypeError, ValueError):
                        pass
            for (pid, _pu), data in consolidated.items():
                PurchaseOrderItem.objects.create(order=instance, product_id=pid, **data)
            # Persistir en Product.amount_boxes si vino amount_boxes en el payload
            for pid, final_boxes in boxes_override_by_product.items():
                try:
                    Product.objects.filter(pk=pid).update(amount_boxes=int(final_boxes))
                except Exception:
                    pass
        return instance

    def _normalize_item(self, item: dict) -> dict:
        """Normaliza el ítem usando únicamente 'purchase_unit'.

        - Convierte quantity_units a int.
        - Acepta 'purchase_unit' o 'unit_type' en el payload.
        - Fuerza purchase_unit = "boxes" (único permitido).
        """
        data = dict(item)
        qty = int(data.get("quantity_units", 0) or 0)
        data["quantity_units"] = qty
        pu = data.get("purchase_unit") or data.get("unit_type") or "boxes"
        # Forzar siempre boxes (única opción soportada)
        data["purchase_unit"] = "boxes"
        return data
