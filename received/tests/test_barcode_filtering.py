"""Tests for barcode filtering in the context of purchase orders."""

import pytest
from rest_framework import status


@pytest.mark.django_db
def test_by_barcode_success(auth_client, purchase_order, product1, barcode1):
    """Should return a single product object for the order and barcode (no persistence)."""
    url = f"/api/received-products/{purchase_order.id}/by-barcode/?barcode={barcode1.code}"
    response = auth_client.get(url)
    
    assert response.status_code == status.HTTP_200_OK
    assert response.data["product_id"] == product1.id
    assert response.data["purchase_order_id"] == purchase_order.id
    assert response.data["barcode_scanned"] == barcode1.code
    assert "quantity_ordered" in response.data
    assert "purchase_unit" in response.data


@pytest.mark.django_db
def test_by_barcode_missing_barcode_param(auth_client, purchase_order):
    """Missing barcode parameter should return 400."""
    url = f"/api/received-products/{purchase_order.id}/by-barcode/"
    response = auth_client.get(url)
    
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "barcode" in response.data["detail"].lower()


@pytest.mark.django_db
def test_by_barcode_purchase_order_not_found(auth_client):
    """Non-existent purchase order should return 404."""
    url = "/api/received-products/99999/by-barcode/?barcode=123456"
    response = auth_client.get(url)
    
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert "purchase order" in response.data["detail"].lower()


@pytest.mark.django_db
def test_by_barcode_not_found(auth_client, purchase_order):
    """Non-existent barcode should return 404."""
    url = f"/api/received-products/{purchase_order.id}/by-barcode/?barcode=9999999999999"
    response = auth_client.get(url)
    
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert "no product found" in response.data["detail"].lower()


@pytest.mark.django_db
def test_by_barcode_product_not_in_order(auth_client, purchase_order, provider):
    """Barcode for a product NOT in the purchase order should return 400 with a specific message."""
    from proveedores.models import Product, ProductBarcode
    
    other_product = Product.objects.create(name="Other Product", sku="OTHER-001")
    other_product.providers.add(provider)
    other_barcode = ProductBarcode.objects.create(
        product=other_product,
        code="5555555555555",
        type=ProductBarcode.BarcodeType.EAN13,
    )
    
    url = f"/api/received-products/{purchase_order.id}/by-barcode/?barcode={other_barcode.code}"
    response = auth_client.get(url)
    
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "not in purchase order" in response.data["detail"].lower()
    assert other_product.name in response.data["detail"]
    assert other_barcode.code in response.data["detail"]
    assert str(purchase_order.id) in response.data["detail"]


@pytest.mark.django_db
def test_by_barcode_returns_object_even_without_received_records(auth_client, purchase_order, product1, barcode1):
    """Valid barcode should return a single object even if there are no received records."""
    url = f"/api/received-products/{purchase_order.id}/by-barcode/?barcode={barcode1.code}"
    response = auth_client.get(url)
    
    assert response.status_code == status.HTTP_200_OK
    assert response.data["product_id"] == product1.id


@pytest.mark.django_db
def test_by_barcode_scoped_to_purchase_order(auth_client, provider, user, product1, barcode1):
    """Filtering is scoped to the specific purchase order id in the URL."""
    from purchase_orders.models import PurchaseOrder, PurchaseOrderItem
    
    po1 = PurchaseOrder.objects.create(provider=provider, ordered_by=user, status="SHIPPED")
    PurchaseOrderItem.objects.create(order=po1, product=product1, quantity_units=5)
    
    po2 = PurchaseOrder.objects.create(provider=provider, ordered_by=user, status="SHIPPED")
    PurchaseOrderItem.objects.create(order=po2, product=product1, quantity_units=3)
    
    url = f"/api/received-products/{po1.id}/by-barcode/?barcode={barcode1.code}"
    response = auth_client.get(url)
    
    assert response.status_code == status.HTTP_200_OK
    assert response.data["purchase_order_id"] == po1.id


@pytest.mark.django_db
def test_by_barcode_case_sensitivity(auth_client, purchase_order, product1):
    """Current implementation is case-sensitive; different case should 404."""
    from proveedores.models import ProductBarcode
    
    ProductBarcode.objects.create(
        product=product1,
        code="ABC123xyz",
        type=ProductBarcode.BarcodeType.CODE128,
    )
    
    url = f"/api/received-products/{purchase_order.id}/by-barcode/?barcode=abc123XYZ"
    response = auth_client.get(url)
    
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_by_barcode_multiple_products_same_order(auth_client, purchase_order, product1, product2, barcode1, barcode2):
    """Query for each product's barcode should return the corresponding product object."""
    # Product1
    url = f"/api/received-products/{purchase_order.id}/by-barcode/?barcode={barcode1.code}"
    res1 = auth_client.get(url)
    assert res1.status_code == status.HTTP_200_OK
    assert res1.data["product_id"] == product1.id
    # Product2
    url = f"/api/received-products/{purchase_order.id}/by-barcode/?barcode={barcode2.code}"
    res2 = auth_client.get(url)
    assert res2.status_code == status.HTTP_200_OK
    assert res2.data["product_id"] == product2.id


@pytest.mark.django_db
def test_by_barcode_authentication_required(api_client, purchase_order, barcode1):
    """Authentication is required for by-barcode endpoint."""
    url = f"/api/received-products/{purchase_order.id}/by-barcode/?barcode={barcode1.code}"
    response = api_client.get(url)
    
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
