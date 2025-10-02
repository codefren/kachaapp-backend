"""Serializers for purchase orders."""

from rest_framework import serializers

from proveedores.models import Product
from .models import PurchaseOrder, PurchaseOrderItem


class PurchaseOrderItemSerializer(serializers.ModelSerializer):
    """Serializer for purchase order items."""
    
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
        """Create a purchase order item and update product amount_boxes if provided."""
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
        """Update a purchase order item and update product amount_boxes if provided."""
        amount_boxes_val = validated_data.pop("amount_boxes", None)
        obj = super().update(instance, validated_data)
        if amount_boxes_val is not None:
            try:
                Product.objects.filter(pk=obj.product_id).update(amount_boxes=int(amount_boxes_val))
            except Exception:
                pass
        return obj

    def to_representation(self, instance):
        """Include amount_boxes from associated product in output."""
        data = super().to_representation(instance)
        # Incluir amount_boxes desde el producto asociado en la salida
        try:
            data["amount_boxes"] = int(getattr(instance.product, "amount_boxes", 0) or 0)
        except Exception:
            data["amount_boxes"] = 0
        return data


class PurchaseOrderSerializer(serializers.ModelSerializer):
    """Serializer for purchase orders."""
    
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
        """Create a purchase order with consolidated items."""
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
                if normalized.get("quantity_units", 0) > 0:
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
        
        # Crear items consolidados (solo si quantity_units > 0)
        for (pid, _pu), data in consolidated.items():
            if data.get("quantity_units", 0) > 0:
                PurchaseOrderItem.objects.create(order=order, product_id=pid, **data)
        
        # Persistir en Product.amount_boxes si vino amount_boxes en el payload
        for pid, final_boxes in boxes_override_by_product.items():
            try:
                Product.objects.filter(pk=pid).update(amount_boxes=int(final_boxes))
            except Exception:
                pass
        return order

    def update(self, instance, validated_data):
        """Update a purchase order and recreate consolidated items."""
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
                    if normalized.get("quantity_units", 0) > 0:
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
            
            # Crear items consolidados (solo si quantity_units > 0)
            for (pid, _pu), data in consolidated.items():
                if data.get("quantity_units", 0) > 0:
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
