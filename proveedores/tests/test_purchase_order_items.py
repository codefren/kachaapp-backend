"""Tests para PurchaseOrderItem."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status

from proveedores.models import PurchaseOrder, PurchaseOrderItem


def test_list_purchase_order_items(auth_client, provider, user, product1, product2):
    """Verifica que se puedan listar purchase order items."""
    # Create a PO to have items
    po = PurchaseOrder.objects.create(provider=provider, ordered_by=user, status="PLACED")
    PurchaseOrderItem.objects.create(order=po, product=product1, quantity_units=3)
    PurchaseOrderItem.objects.create(order=po, product=product2, quantity_units=2)

    url = "/api/purchase-order-items/"
    res = auth_client.get(url)
    assert res.status_code == status.HTTP_200_OK
    assert len(res.data) >= 2
    assert "product" in res.data[0]
    assert "quantity_units" in res.data[0]


def test_purchase_order_item_includes_product_image(auth_client, provider, product1):
    """Verifica que el item incluya la imagen del producto."""
    # Asociar imagen al producto1
    gif_bytes = (
        b"GIF89a"
        b"\x01\x00\x01\x00"
        b"\x80\x00\x00"
        b"\x00\x00\x00"
        b"\x2C\x00\x00\x00\x00\x01\x01\x00\x00"
        b"\x02\x02\x44\x01\x00"
        b"\x3B"
    )
    upload = SimpleUploadedFile("pixel.gif", gif_bytes, content_type="image/gif")
    product1.image.save("pixel.gif", upload, save=True)

    # Crear una orden con un ítem de product1
    url = "/api/purchase-orders/"
    payload = {
        "provider": provider.id,
        "status": "PLACED",
        "items": [
            {"product": product1.id, "quantity_units": 2, "unit_type": "boxes", "amount_boxes": 2},
        ],
    }
    res_create = auth_client.post(url, data=payload, format="json")
    assert res_create.status_code == status.HTTP_201_CREATED
    assert len(res_create.data.get("items", [])) >= 1
    item = res_create.data["items"][0]
    img_url = item.get("product_image")
    assert img_url is not None
    assert img_url.startswith("https://")
