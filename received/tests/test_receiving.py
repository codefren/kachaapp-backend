"""Tests for ReceivingViewSet endpoints.

Endpoints covered:
- POST /api/received-products/{purchase_order_id}/received/
- GET  /api/received-products/{purchase_order_id}/received/

Market is resolved from last LoginHistory of the authenticated user.
"""

import pytest
from rest_framework import status

from market.models import Market, LoginHistory
from received.models import ReceivedProduct, Reception
from proveedores.models import ProductBarcode


@pytest.fixture
@pytest.mark.django_db
def market(provider):
    return Market.objects.create(name="Main Store", latitude=41.0, longitude=2.0)


@pytest.fixture
@pytest.mark.django_db
def login_history(user, market):
    # Record a login history so the view can resolve the user's market
    return LoginHistory.objects.create(
        user=user, market=market, latitude=market.latitude, longitude=market.longitude, event_type=LoginHistory.LOGIN
    )


@pytest.mark.django_db
def test_post_received_success_with_product_id(auth_client, user, purchase_order, product1, login_history):
    url = f"/api/received-products/{purchase_order.id}/received/"
    payload = {
        "items": [
            {"product_id": product1.id, "quantity_received": 3, "is_damaged": False, "notes": "ok"}
        ]
    }
    res = auth_client.post(url, data=payload, format="json")
    assert res.status_code == status.HTTP_200_OK
    assert "reception_id" in res.data

    reception = Reception.objects.get(id=res.data["reception_id"])
    assert reception.purchase_order_id == purchase_order.id
    assert reception.market == login_history.market

    items = ReceivedProduct.objects.filter(reception=reception)
    assert items.count() == 1
    rp = items.first()
    assert rp.product_id == product1.id
    assert rp.quantity_received == 3
    assert rp.market == login_history.market
    assert rp.received_by == user


@pytest.mark.django_db
def test_post_received_success_with_barcode(auth_client, user, purchase_order, product2, barcode2, login_history):
    url = f"/api/received-products/{purchase_order.id}/received/"
    payload = {
        "items": [
            {"barcode": barcode2.code, "quantity_received": 2, "is_damaged": True, "notes": "damaged box"}
        ]
    }
    res = auth_client.post(url, data=payload, format="json")
    assert res.status_code == status.HTTP_200_OK
    reception_id = res.data["reception_id"]

    item = ReceivedProduct.objects.get(reception_id=reception_id)
    assert item.product_id == product2.id
    assert item.quantity_received == 2
    assert item.is_damaged is True
    assert item.notes == "damaged box"


@pytest.mark.django_db
def test_post_received_no_login_history_returns_400(auth_client, purchase_order):
    url = f"/api/received-products/{purchase_order.id}/received/"
    payload = {"items": [{"product_id": 9999, "quantity_received": 1}]}
    res = auth_client.post(url, data=payload, format="json")
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert "no market" in res.data["detail"].lower()


@pytest.mark.django_db
def test_post_received_product_not_in_order_returns_400(auth_client, provider, user, purchase_order, market, login_history):
    # Create another product with barcode not in the order
    from proveedores.models import Product
    other_product = Product.objects.create(name="Other", sku="OTHER-1")
    other_product.providers.add(provider)
    bc = ProductBarcode.objects.create(product=other_product, code="OTHER-BC", type=ProductBarcode.BarcodeType.EAN13)

    url = f"/api/received-products/{purchase_order.id}/received/"
    payload = {"items": [{"barcode": bc.code, "quantity_received": 1}]}
    res = auth_client.post(url, data=payload, format="json")
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert "not in purchase order" in res.data["detail"].lower()


@pytest.mark.django_db
def test_post_received_flags_over_under(auth_client, purchase_order, product1, product2, login_history):
    # ordered: product1=10, product2=5 (from fixture)
    url = f"/api/received-products/{purchase_order.id}/received/"
    payload = {
        "items": [
            {"product_id": product1.id, "quantity_received": 12},  # over
            {"product_id": product2.id, "quantity_received": 3},   # under
        ]
    }
    res = auth_client.post(url, data=payload, format="json")
    assert res.status_code == status.HTTP_200_OK

    rps = ReceivedProduct.objects.filter(reception_id=res.data["reception_id"]).order_by("product_id")
    assert rps.count() == 2
    by_id = {rp.product_id: rp for rp in rps}

    assert by_id[product1.id].is_over_received is True
    assert by_id[product1.id].is_under_received is False

    assert by_id[product2.id].is_over_received is False
    assert by_id[product2.id].is_under_received is True

@pytest.mark.django_db
def test_authentication_required_for_received(api_client, purchase_order):
    url = f"/api/received-products/{purchase_order.id}/received/"
    res_get = api_client.get(url)
    assert res_get.status_code == status.HTTP_401_UNAUTHORIZED

    res_post = api_client.post(url, data={"items": []}, format="json")
    assert res_post.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_post_received_response_shape_only_reception_id(auth_client, purchase_order, product1, login_history):
    """La respuesta del guardado debe ser 200 y solo contener 'reception_id'."""
    url = f"/api/received-products/{purchase_order.id}/received/"
    payload = {"items": [{"product_id": product1.id, "quantity_received": 1}]}
    res = auth_client.post(url, data=payload, format="json")
    assert res.status_code == status.HTTP_200_OK
    assert isinstance(res.data, dict)
    assert set(res.data.keys()) == {"reception_id"}
    assert isinstance(res.data["reception_id"], int)
