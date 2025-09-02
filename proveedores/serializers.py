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
    # Permitir especificar el tipo de unidad al crear: 'units' o 'boxes'.
    # Es de solo escritura; el modelo almacena siempre en unidades.
    unit_type = serializers.ChoiceField(choices=["units", "boxes"], required=False, write_only=True)

    class Meta:
        model = PurchaseOrderItem
        fields = (
            "id",
            "product",
            "product_name",
            "quantity_units",
            "unit_type",
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
    amount_units = serializers.IntegerField(read_only=True)
    amount_boxes = serializers.IntegerField(read_only=True)

    class Meta:
        model = Product
        fields = (
            "id",
            "name",
            "sku",
            "stock_units",
            "units_per_box",
            "amount_units",
            "amount_boxes",
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
        read_only_fields = ("id", "created_at", "updated_at", "ordered_by")

    def create(self, validated_data):
        items_data = validated_data.pop("items", [])
        # Forzar el creador de la orden desde el request
        request = self.context.get("request")
        if request is not None and not request.user.is_anonymous:
            validated_data["ordered_by"] = request.user
        order = PurchaseOrder.objects.create(**validated_data)
        # Consolidar por producto después de normalizar
        consolidated = {}
        boxes_count = {}
        units_count = {}
        for item in items_data:
            # Contabilizar cajas del request antes de normalizar
            try:
                product_ref_req = item.get("product")
                pid_req = product_ref_req.pk if isinstance(product_ref_req, Product) else int(product_ref_req)
                unit_type_req = item.get("unit_type", "units")
                qty_req = int(item.get("quantity_units", 0) or 0)
                if unit_type_req == "boxes":
                    boxes_count[pid_req] = boxes_count.get(pid_req, 0) + qty_req
                elif unit_type_req == "units":
                    units_count[pid_req] = units_count.get(pid_req, 0) + qty_req
            except Exception:
                pass
            normalized = self._normalize_item(item)
            product_ref = normalized.get("product")
            # Resolver id de producto
            try:
                product_id = product_ref.pk if isinstance(product_ref, Product) else int(product_ref)
            except Exception:
                # Si no se puede resolver, inserta tal cual para que validaciones del modelo actúen
                PurchaseOrderItem.objects.create(order=order, **normalized)
                continue
            entry = consolidated.setdefault(product_id, {"quantity_units": 0})
            entry["quantity_units"] += int(normalized.get("quantity_units", 0) or 0)
            # Mantener últimos valores de otros campos no críticos
            if "unit_price" in normalized:
                entry["unit_price"] = normalized["unit_price"]
            if "notes" in normalized:
                entry["notes"] = normalized["notes"]
        for pid, data in consolidated.items():
            item = PurchaseOrderItem.objects.create(order=order, product_id=pid, **data)
            # Actualizar referencia de última compra en el producto
            try:
                product = item.product if hasattr(item, "product") else Product.objects.get(pk=pid)
                # amount_units: unidades solicitadas explícitamente en el request
                product.amount_units = int(units_count.get(pid, 0))
                product.amount_boxes = int(boxes_count.get(pid, 0))
                product.save(update_fields=["amount_units", "amount_boxes", "updated_at"])
            except Exception:
                pass
        return order

    def update(self, instance, validated_data):
        items_data = validated_data.pop("items", None)
        # No permitir cambiar el creador de la orden
        validated_data.pop("ordered_by", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if items_data is not None:
            # Simple strategy: clear and recreate
            instance.items.all().delete()
            consolidated = {}
            boxes_count = {}
            units_count = {}
            for item in items_data:
                # Contabilizar cajas del request antes de normalizar
                try:
                    product_ref_req = item.get("product")
                    pid_req = product_ref_req.pk if isinstance(product_ref_req, Product) else int(product_ref_req)
                    unit_type_req = item.get("unit_type", "units")
                    qty_req = int(item.get("quantity_units", 0) or 0)
                    if unit_type_req == "boxes":
                        boxes_count[pid_req] = boxes_count.get(pid_req, 0) + qty_req
                    elif unit_type_req == "units":
                        units_count[pid_req] = units_count.get(pid_req, 0) + qty_req
                except Exception:
                    pass
                normalized = self._normalize_item(item)
                product_ref = normalized.get("product")
                try:
                    product_id = product_ref.pk if isinstance(product_ref, Product) else int(product_ref)
                except Exception:
                    PurchaseOrderItem.objects.create(order=instance, **normalized)
                    continue
                entry = consolidated.setdefault(product_id, {"quantity_units": 0})
                entry["quantity_units"] += int(normalized.get("quantity_units", 0) or 0)
                if "unit_price" in normalized:
                    entry["unit_price"] = normalized["unit_price"]
                if "notes" in normalized:
                    entry["notes"] = normalized["notes"]
            for pid, data in consolidated.items():
                item = PurchaseOrderItem.objects.create(order=instance, product_id=pid, **data)
                # Actualizar referencia de última compra en el producto
                try:
                    product = item.product if hasattr(item, "product") else Product.objects.get(pk=pid)
                    # amount_units: unidades solicitadas explícitamente en el request
                    product.amount_units = int(units_count.get(pid, 0))
                    product.amount_boxes = int(boxes_count.get(pid, 0))
                    product.save(update_fields=["amount_units", "amount_boxes", "updated_at"])
                except Exception:
                    pass
            return instance

    def _normalize_item(self, item: dict) -> dict:
        """Convierte la entrada del ítem a unidades del modelo.

        - Si unit_type == 'boxes', multiplica quantity_units por units_per_box del producto.
        - Elimina la clave 'unit_type' para que no falle el create() del modelo.
        - Si no viene unit_type, se asume 'units'.
        """
        data = dict(item)  # copiar para no mutar el argumento original
        unit_type = data.pop("unit_type", "units")
        # Asegurar que quantity_units esté presente
        qty = int(data.get("quantity_units", 0) or 0)
        if unit_type == "boxes":
            # Necesitamos conocer units_per_box del producto
            product_ref = data.get("product")
            if product_ref is None:
                return data  # dejar que la validación del modelo falle por falta de producto
            try:
                if isinstance(product_ref, Product):
                    product = product_ref
                else:
                    product = Product.objects.only("id", "units_per_box").get(pk=product_ref)
                qty = qty * (product.units_per_box or 1)
            except Product.DoesNotExist:
                pass  # dejar que falle más adelante en validaciones
        data["quantity_units"] = qty
        return data
