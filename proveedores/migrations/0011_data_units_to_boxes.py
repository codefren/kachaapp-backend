from django.db import migrations
import math


def forwards_convert_units_to_boxes(apps, schema_editor):
    PurchaseOrderItem = apps.get_model('proveedores', 'PurchaseOrderItem')
    Product = apps.get_model('proveedores', 'Product')

    # Obtener IDs de productos a units_per_box para evitar N+1
    units_per_box_map = dict(Product.objects.values_list('id', 'units_per_box'))

    # Filtrar ítems con purchase_unit='units' (si existen en datos históricos)
    items_qs = PurchaseOrderItem.objects.filter(purchase_unit='units')

    for item in items_qs.select_related('order', 'product').iterator():
        upb = int(units_per_box_map.get(item.product_id, 1) or 1)
        qty_units = int(item.quantity_units or 0)
        # Convertir unidades a cajas, redondeando hacia arriba
        if upb <= 0:
            upb = 1
        boxes_to_add = math.ceil(qty_units / upb) if qty_units else 0

        # Intentar fusionar con una línea existente en 'boxes' del mismo (order, product)
        existing_boxes = PurchaseOrderItem.objects.filter(
            order_id=item.order_id,
            product_id=item.product_id,
            purchase_unit='boxes',
        ).first()

        if existing_boxes:
            # Sumar y eliminar la línea en 'units'
            existing_boxes.quantity_units = int(existing_boxes.quantity_units or 0) + boxes_to_add
            existing_boxes.save(update_fields=['quantity_units'])
            item.delete()
        else:
            # Convertir la línea actual a 'boxes'
            item.quantity_units = boxes_to_add
            item.purchase_unit = 'boxes'
            item.save(update_fields=['quantity_units', 'purchase_unit'])


def backwards_convert_boxes_to_units(apps, schema_editor):
    PurchaseOrderItem = apps.get_model('proveedores', 'PurchaseOrderItem')
    Product = apps.get_model('proveedores', 'Product')

    units_per_box_map = dict(Product.objects.values_list('id', 'units_per_box'))

    items_qs = PurchaseOrderItem.objects.filter(purchase_unit='boxes')

    for item in items_qs.select_related('order', 'product').iterator():
        upb = int(units_per_box_map.get(item.product_id, 1) or 1)
        boxes = int(item.quantity_units or 0)
        units = boxes * (upb if upb > 0 else 1)

        # Intentar fusionar con una línea existente en 'units' del mismo (order, product)
        existing_units = PurchaseOrderItem.objects.filter(
            order_id=item.order_id,
            product_id=item.product_id,
            purchase_unit='units',
        ).first()

        if existing_units:
            existing_units.quantity_units = int(existing_units.quantity_units or 0) + units
            existing_units.save(update_fields=['quantity_units'])
            item.delete()
        else:
            item.quantity_units = units
            item.purchase_unit = 'units'
            item.save(update_fields=['quantity_units', 'purchase_unit'])


class Migration(migrations.Migration):

    dependencies = [
        ('proveedores', '0010_remove_product_amount_units_historicalproduct_and_more'),
    ]

    operations = [
        migrations.RunPython(forwards_convert_units_to_boxes, backwards_convert_boxes_to_units),
    ]
