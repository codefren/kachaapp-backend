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
    product_image = serializers.SerializerMethodField()
    purchase_unit = serializers.ChoiceField(choices=["units", "boxes"], required=False)

    class Meta:
        model = PurchaseOrderItem
        fields = (
            "id",
            "product",
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
            # Contabilizar únicamente unidades; boxes ya no se soporta
            try:
                product_ref_req = item.get("product")
                pid_req = product_ref_req.pk if isinstance(product_ref_req, Product) else int(product_ref_req)
                qty_req = int(item.get("quantity_units", 0) or 0)
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
            if "purchase_unit" in normalized:
                entry["purchase_unit"] = normalized["purchase_unit"] or "units"
        for pid, data in consolidated.items():
            item = PurchaseOrderItem.objects.create(order=order, product_id=pid, **data)
            # Actualizar referencia de última compra en el producto
            try:
                product = item.product if hasattr(item, "product") else Product.objects.get(pk=pid)
                # amount_units: unidades solicitadas explícitamente en el request
                product.amount_units = int(units_count.get(pid, 0))
                product.amount_boxes = 0
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
                # Contabilizar únicamente unidades; boxes ya no se soporta
                try:
                    product_ref_req = item.get("product")
                    pid_req = product_ref_req.pk if isinstance(product_ref_req, Product) else int(product_ref_req)
                    qty_req = int(item.get("quantity_units", 0) or 0)
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
                if "notes" in normalized:
                    entry["notes"] = normalized["notes"]
                if "purchase_unit" in normalized:
                    entry["purchase_unit"] = normalized["purchase_unit"] or "units"
            for pid, data in consolidated.items():
                item = PurchaseOrderItem.objects.create(order=instance, product_id=pid, **data)
                # Actualizar referencia de última compra en el producto
                try:
                    product = item.product if hasattr(item, "product") else Product.objects.get(pk=pid)
                    # amount_units: unidades solicitadas explícitamente en el request
                    product.amount_units = int(units_count.get(pid, 0))
                    product.amount_boxes = 0
                    product.save(update_fields=["amount_units", "amount_boxes", "updated_at"])
                except Exception:
                    pass
        return instance

    def _normalize_item(self, item: dict) -> dict:
        """Normaliza la entrada del ítem sin conversión por cajas.

        - Se asegura que quantity_units sea un entero.
        - Ignora cualquier clave ajena legacy (p.ej. unit_type) si viene en el payload.
        - Acepta purchase_unit (units|boxes) y aplica default 'units' si no viene.
        """
        data = dict(item)  # copiar para no mutar el argumento original
        qty = int(data.get("quantity_units", 0) or 0)
        data["quantity_units"] = qty
        # Legacy: Remover unit_type si viene para evitar fallos en create()
        data.pop("unit_type", None)
        # purchase_unit opcional; default 'units'
        pu = data.get("purchase_unit")
        if pu not in ("units", "boxes"):
            data["purchase_unit"] = "units"
        return data
