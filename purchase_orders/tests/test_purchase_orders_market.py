"""Tests for market association on Purchase Orders.

Verifica que:
- Al crear una orden, se toma el market del último LoginHistory del usuario.
- Si no existe LoginHistory para el usuario, la creación falla (400).
- No se permite cambiar el market vía update/patch del pedido.
"""

import pytest
from rest_framework import status

from market.models import Market, LoginHistory
from purchase_orders.models import PurchaseOrder


@pytest.mark.django_db
def test_create_purchase_order_sets_market_from_login_history(auth_client, provider, user, product1):
    """Crear PO debe asignar market desde el último LoginHistory del usuario y devolverlo en la respuesta."""
    # Arrange: crear un market y un login history para el usuario
    market = Market.objects.create(name="Mercado Central", latitude=41.387, longitude=2.170)
    LoginHistory.objects.create(user=user, market=market, latitude=41.387, longitude=2.170, event_type=LoginHistory.LOGIN)

    url = "/api/purchase-orders/"
    payload = {
        "provider": provider.id,
        "status": "PLACED",
        "notes": "Con market via LoginHistory",
        "items": [
            {"product": product1.id, "quantity_units": 3, "unit_type": "boxes", "amount_boxes": 3},
        ],
    }

    # Act
    res = auth_client.post(url, data=payload, format="json")

    # Assert
    assert res.status_code == status.HTTP_201_CREATED
    assert res.data.get("market") == market.id

    po = PurchaseOrder.objects.get(id=res.data["id"])
    assert po.market_id == market.id


@pytest.mark.django_db
def test_create_purchase_order_without_login_history_fails(auth_client, provider, user, product1):
    """Si el usuario no tiene LoginHistory, crear PO debe fallar con 400 y error en campo market."""
    # Asegurar que no haya historial
    LoginHistory.objects.filter(user=user).delete()

    url = "/api/purchase-orders/"
    payload = {
        "provider": provider.id,
        "status": "PLACED",
        "items": [
            {"product": product1.id, "quantity_units": 1, "unit_type": "boxes"},
        ],
    }

    res = auth_client.post(url, data=payload, format="json")

    assert res.status_code == status.HTTP_400_BAD_REQUEST
    # Puede venir como dict de errores; validar clave market
    assert "market" in res.data


@pytest.mark.django_db
def test_update_purchase_order_cannot_change_market(auth_client, provider, user, product1):
    """Intentar cambiar market en PATCH no debe modificar el market existente."""
    # Arrange: crear market A y B, y login history para A
    market_a = Market.objects.create(name="Mercado A", latitude=41.387, longitude=2.170)
    market_b = Market.objects.create(name="Mercado B", latitude=41.388, longitude=2.171)
    LoginHistory.objects.create(user=user, market=market_a, latitude=41.387, longitude=2.170, event_type=LoginHistory.LOGIN)

    # Crear la orden (asigna A)
    create_url = "/api/purchase-orders/"
    create_payload = {
        "provider": provider.id,
        "status": "PLACED",
        "items": [
            {"product": product1.id, "quantity_units": 2, "unit_type": "boxes"},
        ],
    }
    res_create = auth_client.post(create_url, data=create_payload, format="json")
    assert res_create.status_code == status.HTTP_201_CREATED
    po_id = res_create.data["id"]

    # Act: intentar cambiar el market a B vía PATCH
    patch_url = f"/api/purchase-orders/{po_id}/"
    patch_payload = {"market": market_b.id, "notes": "Intento de cambio de market"}
    res_patch = auth_client.patch(patch_url, data=patch_payload, format="json")

    # Assert: petición exitosa pero market no cambia
    assert res_patch.status_code in (status.HTTP_200_OK, status.HTTP_202_ACCEPTED)
    assert res_patch.data.get("market") == market_a.id

    po = PurchaseOrder.objects.get(id=po_id)
    assert po.market_id == market_a.id
