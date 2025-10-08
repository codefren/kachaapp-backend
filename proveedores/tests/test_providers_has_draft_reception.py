"""Tests for providers list including has_draft_reception flag.

The flag indicates whether there exists a Reception in DRAFT status for any
purchase order of the provider in the current user's market (from LoginHistory).
"""

import pytest
from rest_framework import status

from market.models import Market, LoginHistory
from purchase_orders.models import PurchaseOrder
from received.models import Reception
from proveedores.models import Provider


@pytest.fixture
@pytest.mark.django_db
def market():
    return Market.objects.create(name="Test Market", latitude=41.4, longitude=2.1)


@pytest.fixture
@pytest.mark.django_db
def login_history(user, market):
    return LoginHistory.objects.create(
        user=user,
        market=market,
        latitude=market.latitude,
        longitude=market.longitude,
        event_type=LoginHistory.LOGIN,
    )


@pytest.mark.django_db
def test_providers_list_has_draft_reception_true_false(auth_client, user, provider, market, login_history):
    # Provider A from fixture should have a DRAFT reception
    po_a = PurchaseOrder.objects.create(provider=provider, ordered_by=user, market=market, status=PurchaseOrder.Status.SHIPPED)

    Reception.objects.create(purchase_order=po_a, market=market, received_by=user, status=Reception.Status.DRAFT)

    # Create another provider B without reception (include required fields)
    from datetime import time
    provider_b = Provider.objects.create(
        name="Proveedor B",
        order_deadline_time=time(14, 0),
        order_available_weekdays=[0, 1, 2, 3, 4],
    )

    res = auth_client.get("/api/providers/")
    assert res.status_code == status.HTTP_200_OK
    assert isinstance(res.data, list)

    by_id = {p["id"]: p for p in res.data}
    assert by_id[provider.id]["has_draft_reception"] is True
    assert by_id[provider.id]["draft_reception_order_id"] == po_a.id
    assert by_id[provider_b.id]["has_draft_reception"] is False
    assert by_id[provider_b.id]["draft_reception_order_id"] is None
    # last_shipped_order_id debe ser el id de la última PO SHIPPED en el market del usuario
    assert by_id[provider.id]["last_shipped_order_id"] == po_a.id
    assert by_id[provider_b.id]["last_shipped_order_id"] is None


@pytest.mark.django_db
def test_providers_list_has_draft_reception_other_market_false(auth_client, user, provider, market, login_history):
    # Create PO for provider in current user market but create Reception in a different market
    po = PurchaseOrder.objects.create(provider=provider, ordered_by=user, market=market, status=PurchaseOrder.Status.SHIPPED)

    other_market = Market.objects.create(name="Other Market", latitude=40.0, longitude=1.0)
    Reception.objects.create(purchase_order=po, market=other_market, received_by=user, status=Reception.Status.DRAFT)

    res = auth_client.get("/api/providers/")
    assert res.status_code == status.HTTP_200_OK
    assert isinstance(res.data, list)
    item = next(p for p in res.data if p["id"] == provider.id)
    assert item["has_draft_reception"] is False
    assert item["draft_reception_order_id"] is None
    # Aunque la recepción está en otro market, la última SHIPPED en el market del usuario debe reflejarse
    assert item["last_shipped_order_id"] == po.id


@pytest.mark.django_db
def test_providers_list_has_draft_reception_completed_is_false(auth_client, user, provider, market, login_history):
    # Create only COMPLETED reception -> flag must be False
    po = PurchaseOrder.objects.create(provider=provider, ordered_by=user, market=market, status=PurchaseOrder.Status.SHIPPED)
    Reception.objects.create(purchase_order=po, market=market, received_by=user, status=Reception.Status.COMPLETED)

    res = auth_client.get("/api/providers/")
    assert res.status_code == status.HTTP_200_OK
    item = next(p for p in res.data if p["id"] == provider.id)
    assert item["has_draft_reception"] is False
    # last_shipped_order_id sigue reflejando la última SHIPPED
    assert item["last_shipped_order_id"] == po.id


@pytest.mark.django_db
def test_providers_list_requires_login_history(auth_client, user, provider):
    # Asegurar que NO haya LoginHistory para este usuario (auth_client lo crea)
    LoginHistory.objects.filter(user=user).delete()

    res = auth_client.get("/api/providers/")
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert "no market" in res.data["detail"].lower()
