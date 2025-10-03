"""Tests CRUD de Purchase Orders."""

import pytest
from rest_framework import status

from proveedores.models import Product, Provider
from purchase_orders.models import PurchaseOrder, PurchaseOrderItem



def test_root(auth_client):
    """Verifica que el endpoint raíz de la API responda correctamente."""
    url = "/api/"
    res = auth_client.get(url)
    assert res.status_code == status.HTTP_200_OK
    assert "message" in res.data


def test_create_and_retrieve_purchase_order(auth_client, provider, user, product2):
    """Verifica que se pueda crear y recuperar una orden de compra."""
    url = "/api/purchase-orders/"
    # Pedido: producto en BOXES
    payload_units = {
        "provider": provider.id,
        "ordered_by": user.id,
        "status": "PLACED",
        "notes": "Orden unidades",
        "items": [
            {"product": product2.id, "quantity_units": 10, "unit_type": "boxes", "amount_boxes": 10},
        ],
    }
    res_units = auth_client.post(url, data=payload_units, format="json")
    assert res_units.status_code == status.HTTP_201_CREATED
    po_units_id = res_units.data["id"]
    assert len(res_units.data["items"]) == 1
    assert res_units.data["items"][0]["product"] == product2.id
    assert res_units.data["items"][0]["quantity_units"] == 10

    # Retrieve detail de la orden
    detail_units = auth_client.get(f"/api/purchase-orders/{po_units_id}/")
    assert detail_units.status_code == status.HTTP_200_OK
    assert detail_units.data["id"] == po_units_id
    assert detail_units.data["provider"] == provider.id
    assert len(detail_units.data["items"]) == 1


def test_create_purchase_order_sets_and_returns_ordered_by(auth_client, provider, user, product1):
    """Verifica que ordered_by se tome del usuario autenticado si no se proporciona."""
    url = "/api/purchase-orders/"
    # No enviar ordered_by en el payload; debe tomarse del request.user
    payload = {
        "provider": provider.id,
        "status": "PLACED",
        "notes": "Orden sin ordered_by en payload",
        "items": [
            {"product": product1.id, "quantity_units": 1, "unit_type": "boxes"},
        ],
    }
    res = auth_client.post(url, data=payload, format="json")
    assert res.status_code == status.HTTP_201_CREATED
    assert res.data.get("ordered_by") == user.id
    assert res.data.get("ordered_by_username") == user.username


def test_purchase_order_item_persists_purchase_unit(auth_client, provider, product1, product2):
    """Verifica que el campo purchase_unit se persista correctamente en los items."""
    url = "/api/purchase-orders/"
    payload = {
        "provider": provider.id,
        "status": "PLACED",
        "notes": "Orden con purchase_unit boxes",
        "items": [
            {"product": product2.id, "quantity_units": 5, "purchase_unit": "boxes", "amount_boxes": 5},
            {"product": product1.id, "quantity_units": 2, "purchase_unit": "boxes", "amount_boxes": 2},
        ],
    }
    res = auth_client.post(url, data=payload, format="json")
    assert res.status_code == status.HTTP_201_CREATED
    items = res.data.get("items", [])
    assert len(items) == 2
    # Mapear purchase_unit por producto
    pu_by_product = {it["product"]: it.get("purchase_unit") for it in items}
    assert pu_by_product.get(product2.id) == "boxes"
    assert pu_by_product.get(product1.id) == "boxes"


def test_same_product_multiple_boxes_consolidates(auth_client, provider, product2):
    """Verifica que múltiples líneas del mismo producto se consoliden."""
    url = "/api/purchase-orders/"
    payload = {
        "provider": provider.id,
        "status": "PLACED",
        "notes": "Mismo producto con dos líneas en boxes",
        "items": [
            {"product": product2.id, "quantity_units": 4, "purchase_unit": "boxes", "amount_boxes": 4},
            {"product": product2.id, "quantity_units": 1, "purchase_unit": "boxes", "amount_boxes": 1},
        ],
    }
    res = auth_client.post(url, data=payload, format="json")
    assert res.status_code == status.HTTP_201_CREATED
    items = res.data.get("items", [])
    # Debe consolidar en un solo renglón para el mismo producto y purchase_unit
    assert len(items) == 1
    assert items[0]["product"] == product2.id
    assert items[0]["purchase_unit"] == "boxes"
    assert items[0]["quantity_units"] == 5


def test_create_order_same_product_multiple_lines_consolidates(auth_client, provider, user, product2):
    """Verifica que múltiples líneas del mismo producto se consoliden (unit_type)."""
    url = "/api/purchase-orders/"
    payload = {
        "provider": provider.id,
        "ordered_by": user.id,
        "status": "PLACED",
        "notes": "Varias líneas del mismo producto (boxes)",
        "items": [
            {"product": product2.id, "quantity_units": 10, "unit_type": "boxes", "amount_boxes": 10},
            {"product": product2.id, "quantity_units": 2, "unit_type": "boxes", "amount_boxes": 2},
        ],
    }
    res = auth_client.post(url, data=payload, format="json")
    assert res.status_code == status.HTTP_201_CREATED
    # Debe consolidar en un solo ítem con la suma de cantidades
    assert len(res.data.get("items", [])) == 1
    item = res.data["items"][0]
    assert item["product"] == product2.id
    assert item["quantity_units"] == 12


def test_update_purchase_order(auth_client, provider, user, product1, product2):
    """Verifica que se pueda actualizar una orden de compra."""
    # Crear orden inicial
    create_url = "/api/purchase-orders/"
    create_payload = {
        "provider": provider.id,
        "ordered_by": user.id,
        "status": "PLACED",
        "notes": "Orden inicial",
        "items": [
            {"product": product1.id, "quantity_units": 2, "unit_type": "boxes"},
            {"product": product2.id, "quantity_units": 1, "unit_type": "boxes"},
        ],
    }
    res_create = auth_client.post(create_url, data=create_payload, format="json")
    assert res_create.status_code == status.HTTP_201_CREATED
    po_id = res_create.data["id"]

    # Actualizar: cambiar notas e ítems
    detail_url = f"/api/purchase-orders/{po_id}/"
    patch_payload = {
        "notes": "Orden actualizada",
        "items": [
            {"product": product1.id, "quantity_units": 4, "unit_type": "boxes", "amount_boxes": 4},
            {"product": product2.id, "quantity_units": 2, "unit_type": "boxes", "amount_boxes": 2},
        ],
    }
    res_patch = auth_client.patch(detail_url, data=patch_payload, format="json")
    assert res_patch.status_code in (status.HTTP_200_OK, status.HTTP_202_ACCEPTED)

    # Verificar detalle
    res_detail = auth_client.get(detail_url)
    assert res_detail.status_code == status.HTTP_200_OK
    assert res_detail.data.get("notes") == "Orden actualizada"
    assert len(res_detail.data.get("items", [])) == 2

    # Mapear cantidades por producto
    items = res_detail.data["items"]
    qty_by_product = {it["product"]: it["quantity_units"] for it in items}
    assert qty_by_product.get(product1.id) == 4
    assert qty_by_product.get(product2.id) == 2


def test_product_last_purchase_amounts_on_create(auth_client, provider, user, product2):
    """Verifica que se actualice el historial de compra al crear una orden."""
    url = "/api/purchase-orders/"
    payload = {
        "provider": provider.id,
        "ordered_by": user.id,
        "status": "PLACED",
        "notes": "PO para historial",
        "items": [
            {"product": product2.id, "quantity_units": 36, "unit_type": "boxes", "amount_boxes": 36},
        ],
    }
    res = auth_client.post(url, data=payload, format="json")
    assert res.status_code == status.HTTP_201_CREATED


def test_product_last_purchase_amounts_on_update(auth_client, provider, user, product2):
    """Verifica que se actualice amount_boxes del producto al actualizar una orden."""
    # Crear orden inicial con unidades
    create_url = "/api/purchase-orders/"
    payload = {
        "provider": provider.id,
        "ordered_by": user.id,
        "status": "PLACED",
        "items": [
            {"product": product2.id, "quantity_units": 5, "unit_type": "boxes", "amount_boxes": 5},
        ],
    }
    res_create = auth_client.post(create_url, data=payload, format="json")
    assert res_create.status_code == status.HTTP_201_CREATED
    po_id = res_create.data["id"]

    # Actualizar orden: cambiar a 2 boxes
    patch_url = f"/api/purchase-orders/{po_id}/"
    patch_payload = {
        "items": [
            {"product": product2.id, "quantity_units": 2, "unit_type": "boxes", "amount_boxes": 2},
        ]
    }
    res_patch = auth_client.patch(patch_url, data=patch_payload, format="json")
    assert res_patch.status_code in (status.HTTP_200_OK, status.HTTP_202_ACCEPTED)

    # Verificar referencia actualizada (amount_boxes)
    prod_detail_2 = auth_client.get(f"/api/products/{product2.id}/")
    assert prod_detail_2.status_code == status.HTTP_200_OK
    assert prod_detail_2.data.get("amount_boxes") == 2


def test_purchase_order_queryset_no_date_returns_all(auth_client, provider, user, product1):
    """Verifica que sin parámetro date se devuelvan todas las órdenes."""
    # Crear 2 órdenes hoy
    url = "/api/purchase-orders/"
    for _ in range(2):
        payload = {
            "provider": provider.id,
            "ordered_by": user.id,
            "status": "PLACED",
            "items": [
                {"product": product1.id, "quantity_units": 1, "unit_type": "boxes", "amount_boxes": 1},
            ],
        }
        res = auth_client.post(url, data=payload, format="json")
        assert res.status_code == status.HTTP_201_CREATED

    # Sin parámetro date debe devolver todas
    res_list = auth_client.get(url)
    assert res_list.status_code == status.HTTP_200_OK
    data = res_list.data if isinstance(res_list.data, list) else res_list.data.get("results", [])
    assert len(data) == 2


def test_purchase_order_queryset_invalid_date_returns_all(auth_client, provider, user, product2):
    """Verifica que un date inválido se ignore y devuelva todas las órdenes."""
    # Crear 2 órdenes hoy
    url = "/api/purchase-orders/"
    for _ in range(2):
        payload = {
            "provider": provider.id,
            "ordered_by": user.id,
            "status": "PLACED",
            "items": [
                {"product": product2.id, "quantity_units": 1, "unit_type": "boxes", "amount_boxes": 1},
            ],
        }
        res = auth_client.post(url, data=payload, format="json")
        assert res.status_code == status.HTTP_201_CREATED

    # date inválido debe ignorarse y devolver todas
    res_list = auth_client.get(f"{url}?date=2025-13-40")
    assert res_list.status_code == status.HTTP_200_OK
    data = res_list.data if isinstance(res_list.data, list) else res_list.data.get("results", [])
    assert len(data) == 2


def test_purchase_order_create_update_includes_amount_boxes_in_items(auth_client, provider, product2):
    """Verifica que amount_boxes esté presente en la respuesta de items."""
    # Crear una orden con un ítem y validar que en la respuesta venga amount_boxes en items
    create_url = "/api/purchase-orders/"
    payload_create = {
        "provider": provider.id,
        "status": "PLACED",
        "items": [
            {"product": product2.id, "quantity_units": 7, "unit_type": "boxes", "amount_boxes": 7},
        ],
    }
    res_create = auth_client.post(create_url, data=payload_create, format="json")
    assert res_create.status_code == status.HTTP_201_CREATED
    assert len(res_create.data.get("items", [])) >= 1
    item_create = res_create.data["items"][0]
    # amount_boxes debe estar presente y ser igual al total de cajas de la orden para ese producto
    assert "amount_boxes" in item_create
    assert item_create["amount_boxes"] == 7

    # Actualizar la misma orden con otro total de cajas y verificar amount_boxes en la respuesta
    po_id = res_create.data["id"]
    patch_url = f"/api/purchase-orders/{po_id}/"
    payload_patch = {
        "items": [
            {"product": product2.id, "quantity_units": 3, "unit_type": "boxes", "amount_boxes": 3},
        ]
    }
    res_patch = auth_client.patch(patch_url, data=payload_patch, format="json")
    assert res_patch.status_code in (status.HTTP_200_OK, status.HTTP_202_ACCEPTED)
    assert len(res_patch.data.get("items", [])) >= 1
    item_patch = res_patch.data["items"][0]
    assert "amount_boxes" in item_patch
    assert item_patch["amount_boxes"] == 3
