"""Tests for ReceptionViewSet (retrieve and partial_update)."""

import pytest
from rest_framework import status

from market.models import Market, LoginHistory
from purchase_orders.models import PurchaseOrder, PurchaseOrderItem
from received.models import Reception, ReceivedProduct
from proveedores.models import Product
from proveedores.models import ProductBarcode


@pytest.fixture
@pytest.mark.django_db
def market():
    return Market.objects.create(name="Market A", latitude=41.0, longitude=2.0)


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


def _create_reception_with_items(user, market, purchase_order, product_qty_pairs):
    reception = Reception.objects.create(purchase_order=purchase_order, market=market, received_by=user)
    items = []
    for product, qty in product_qty_pairs:
        # compute flags vs ordered
        poi = PurchaseOrderItem.objects.get(order=purchase_order, product=product)
        is_over = qty > (poi.quantity_units or 0)
        is_under = qty < (poi.quantity_units or 0)
        items.append(
            ReceivedProduct.objects.create(
                purchase_order=purchase_order,
                product=product,
                market=market,
                reception=reception,
                quantity_received=qty,
                is_damaged=False,
                notes="",
                received_by=user,
                is_over_received=is_over,
                is_under_received=is_under,
            )
        )
    return reception, items


@pytest.mark.django_db
def test_reception_retrieve_ok(auth_client, user, purchase_order, product1, product2, login_history, market):
    # Arrange: create a DRAFT reception with two items
    reception, items = _create_reception_with_items(
        user, market, purchase_order, [(product1, 3), (product2, 1)]
    )

    # Act
    url = f"/api/receptions/{reception.id}/"
    res = auth_client.get(url)

    # Assert
    assert res.status_code == status.HTTP_200_OK
    assert res.data["id"] == reception.id
    assert res.data["purchase_order_id"] == purchase_order.id
    assert res.data["market_id"] == market.id
    assert res.data["status"] == Reception.Status.DRAFT
    assert isinstance(res.data["items"], list)
    assert len(res.data["items"]) == 2


@pytest.mark.django_db
def test_reception_retrieve_requires_login_history(auth_client, user, purchase_order, product1, product2, market):
    reception, _ = _create_reception_with_items(user, market, purchase_order, [(product1, 1)])

    url = f"/api/receptions/{reception.id}/"
    res = auth_client.get(url)
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert "no market" in res.data["detail"].lower()


@pytest.mark.django_db
def test_reception_retrieve_forbidden_other_market(auth_client, user, purchase_order, product1, market, login_history):
    other_market = Market.objects.create(name="Other Mkt", latitude=41.5, longitude=2.1)
    reception, _ = _create_reception_with_items(user, other_market, purchase_order, [(product1, 1)])

    url = f"/api/receptions/{reception.id}/"
    res = auth_client.get(url)
    assert res.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_reception_patch_status_only(auth_client, user, purchase_order, product1, login_history, market):
    reception, _ = _create_reception_with_items(user, market, purchase_order, [(product1, 2)])

    url = f"/api/receptions/{reception.id}/"
    res = auth_client.patch(url, data={"status": Reception.Status.COMPLETED}, format="json")
    assert res.status_code == status.HTTP_200_OK
    assert res.data["reception_id"] == reception.id
    assert res.data["status"] == Reception.Status.COMPLETED

    # Items remain intact
    assert ReceivedProduct.objects.filter(reception=reception).count() == 1


@pytest.mark.django_db
def test_reception_patch_replace_items_happy_path_allows_zero(auth_client, user, purchase_order, product1, product2, login_history, market):
    # existing reception with one item
    reception, _ = _create_reception_with_items(user, market, purchase_order, [(product1, 2)])

    payload = {
        "items": [
            {"product_id": product1.id, "quantity_received": 0},  # allowed now
            {"product_id": product2.id, "quantity_received": 12, "is_damaged": True, "notes": "over"}
        ]
    }
    url = f"/api/receptions/{reception.id}/"
    res = auth_client.patch(url, data=payload, format="json")
    assert res.status_code == status.HTTP_200_OK

    # Items replaced
    new_items = list(ReceivedProduct.objects.filter(reception=reception).order_by("product_id"))
    assert len(new_items) == 2
    by_id = {i.product_id: i for i in new_items}

    # product1 ordered 10 per fixture -> qty 0 => under True
    assert by_id[product1.id].quantity_received == 0
    assert by_id[product1.id].is_under_received is True

    # product2 ordered 5 per fixture -> qty 12 => over True
    assert by_id[product2.id].quantity_received == 12
    assert by_id[product2.id].is_over_received is True
    assert by_id[product2.id].is_damaged is True
    assert by_id[product2.id].notes == "over"


@pytest.mark.django_db
def test_reception_patch_replace_items_when_completed_fails(auth_client, user, purchase_order, product1, login_history, market):
    reception, _ = _create_reception_with_items(user, market, purchase_order, [(product1, 2)])
    reception.status = Reception.Status.COMPLETED
    reception.save(update_fields=["status"])

    url = f"/api/receptions/{reception.id}/"
    res = auth_client.patch(url, data={"items": [{"product_id": product1.id, "quantity_received": 1}]}, format="json")
    assert res.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_reception_patch_replace_items_invalid_product(auth_client, user, provider, purchase_order, product1, login_history, market):
    # product not in order
    other_product = Product.objects.create(name="Other", sku="OTHER-1")
    other_product.providers.add(provider)

    reception, _ = _create_reception_with_items(user, market, purchase_order, [(product1, 2)])

    url = f"/api/receptions/{reception.id}/"
    res = auth_client.patch(url, data={"items": [{"product_id": other_product.id, "quantity_received": 1}]}, format="json")
    assert res.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_reception_patch_replace_items_invalid_barcode(auth_client, user, purchase_order, product1, login_history, market):
    reception, _ = _create_reception_with_items(user, market, purchase_order, [(product1, 2)])

    url = f"/api/receptions/{reception.id}/"
    res = auth_client.patch(url, data={"items": [{"barcode": "UNKNOWN", "quantity_received": 1}]}, format="json")
    assert res.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_reception_patch_replace_items_negative_quantity(auth_client, user, purchase_order, product1, login_history, market):
    reception, _ = _create_reception_with_items(user, market, purchase_order, [(product1, 2)])

    url = f"/api/receptions/{reception.id}/"
    res = auth_client.patch(url, data={"items": [{"product_id": product1.id, "quantity_received": -1}]}, format="json")
    assert res.status_code == status.HTTP_400_BAD_REQUEST
