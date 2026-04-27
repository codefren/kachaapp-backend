"""Serializers for purchase orders."""

from rest_framework import serializers

from proveedores.models import Product
from .models import PurchaseOrder, PurchaseOrderItem
from market.models import LoginHistory


class PurchaseOrderItemSerializer(serializers.ModelSerializer):
    """Serializer for purchase order items."""

    product_name = serializers.CharField(source="product.name", read_only=True)
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
        try:
            data["amount_boxes"] = int(getattr(instance.product, "amount_boxes", 0) or 0)
        except Exception:
            data["amount_boxes"] = 0
        return data


class PurchaseOrderSerializer(serializers.ModelSerializer):
    """Serializer for purchase orders."""

    provider_name = serializers.CharField(source="provider.name", read_only=True)
    market_name = serializers.CharField(source="market.name", read_only=True)    
    ordered_by_username = serializers.CharField(source="ordered_by.username", read_only=True)
    items = PurchaseOrderItemSerializer(many=True, required=False)
    sent_by_username = serializers.CharField(source="sent_by.username", read_only=True)

    locked_by_username = serializers.CharField(source="locked_by.username", read_only=True)
    is_locked = serializers.SerializerMethodField()
    lock_expires_at = serializers.SerializerMethodField()

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
            "market",
            "market_name",   
            "items",
            "sent_at",
            "sent_to_email",
            "sent_by",
            "sent_by_username",
            "locked_by",
            "locked_by_username",
            "is_locked",
            "lock_expires_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "ordered_by",
            "created_at",
            "updated_at",
            "sent_at",
            "sent_to_email",
            "sent_by",
            "sent_by_username",
            "locked_by",
            "locked_by_username",
            "is_locked",
            "lock_expires_at",
        )

    def get_is_locked(self, obj):
        obj.clear_expired_lock(save=False)
        return obj.is_locked

    def get_lock_expires_at(self, obj):
        obj.clear_expired_lock(save=False)
        return obj.lock_expires_at

    def create(self, validated_data):
        items_data = validated_data.pop("items", [])
        request = self.context.get("request")
        if request is not None and not request.user.is_anonymous:
            validated_data["ordered_by"] = request.user
            # Usar el shift activo del usuario para asignar el market
            from market.models import Shift
            active_shift = Shift.objects.filter(
                user=request.user,
                ended_at__isnull=True,
            ).select_related("market").first()

            if active_shift and active_shift.market:
                validated_data["market"] = active_shift.market
            else:
                # Fallback: último login history
                last = (
                    LoginHistory.objects.select_related("market")
                    .filter(user=request.user)
                    .order_by("-timestamp")
                    .only("market_id")
                    .first()
                )
                if not last or not last.market_id:
                    raise serializers.ValidationError({"market": "No market found for current user (no login history)."})
                validated_data["market"] = last.market

        # Verificar si ya existe un pedido activo para este proveedor y market
        from django.db.models import Q
        existing = PurchaseOrder.objects.filter(
            provider=validated_data.get('provider'),
            market=validated_data.get('market'),
            sent_at__isnull=True,
        ).filter(
            Q(status=PurchaseOrder.Status.PLACED) | Q(status=PurchaseOrder.Status.DRAFT)
        ).order_by('-created_at').first()

        if existing:
            # Reutilizar pedido existente — actualizar ordered_by y market
            if 'ordered_by' in validated_data:
                existing.ordered_by = validated_data['ordered_by']
            if 'market' in validated_data:
                existing.market = validated_data['market']
            existing.save(update_fields=['ordered_by', 'market', 'updated_at'])
            order = existing
        else:
            order = PurchaseOrder.objects.create(**validated_data)

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
                    PurchaseOrderItem.objects.create(order=order, **normalized)
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
            if data.get("quantity_units", 0) > 0:
                PurchaseOrderItem.objects.create(order=order, product_id=pid, **data)

        for pid, final_boxes in boxes_override_by_product.items():
            try:
                Product.objects.filter(pk=pid).update(amount_boxes=int(final_boxes))
            except Exception:
                pass
        return order

    def update(self, instance, validated_data):
        items_data = validated_data.pop("items", None)
        validated_data.pop("market", None)
        validated_data.pop("ordered_by", None)

        request = self.context.get("request")
        if instance.is_locked and instance.locked_by_id and request and instance.locked_by_id != request.user.id:
            raise serializers.ValidationError(
                {"detail": "Este pedido está bloqueado por otro usuario: {}.".format(instance.locked_by.username)}
            )

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if items_data is not None:
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

            for (pid, _pu), data in consolidated.items():
                if data.get("quantity_units", 0) > 0:
                    PurchaseOrderItem.objects.create(order=instance, product_id=pid, **data)

            for pid, final_boxes in boxes_override_by_product.items():
                try:
                    Product.objects.filter(pk=pid).update(amount_boxes=int(final_boxes))
                except Exception:
                    pass
        return instance

    def _normalize_item(self, item: dict) -> dict:
        data = dict(item)
        qty = int(data.get("quantity_units", 0) or 0)
        data["quantity_units"] = qty
        data["purchase_unit"] = "boxes"
        return data
