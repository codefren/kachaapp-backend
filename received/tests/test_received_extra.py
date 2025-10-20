"""Tests for received-extra endpoint.

Endpoint covered:
- POST /api/received-products/{purchase_order_id}/received-extra/

Tests registering products that are NOT in the original purchase order.
"""

import pytest
from rest_framework import status

from market.models import Market, LoginHistory
from received.models import ReceivedProduct, Reception
from proveedores.models import Product, ProductBarcode


@pytest.fixture
@pytest.mark.django_db
def market(provider):
    return Market.objects.create(name="Main Store", latitude=41.0, longitude=2.0)


@pytest.fixture
@pytest.mark.django_db
def login_history(user, market):
    # Record a login history so the view can resolve the user's market
    return LoginHistory.objects.create(
        user=user, 
        market=market, 
        latitude=market.latitude, 
        longitude=market.longitude, 
        event_type=LoginHistory.LOGIN
    )


@pytest.fixture
@pytest.mark.django_db
def extra_product(provider):
    """Product that is NOT in any purchase order"""
    product = Product.objects.create(
        name="Extra Product Not Ordered",
        sku="EXTRA001",
        amount_boxes=5
    )
    product.providers.add(provider)
    return product


@pytest.fixture
@pytest.mark.django_db
def extra_product_with_barcode(provider):
    """Extra product with barcode"""
    product = Product.objects.create(
        name="Extra Product with Barcode",
        sku="EXTRA002", 
        amount_boxes=3
    )
    product.providers.add(provider)
    ProductBarcode.objects.create(product=product, code="9876543210")
    return product


@pytest.mark.django_db
def test_received_extra_success_with_product_id(auth_client, purchase_order, extra_product, login_history):
    """Test registering extra product by product_id"""
    url = f"/api/received-products/{purchase_order.id}/received-extra/"
    payload = {
        "product_id": extra_product.id,
        "quantity_received": 3,
        "is_damaged": False,
        "notes": "Producto promocional del proveedor",
        "reason": "PROMOTIONAL"
    }
    
    res = auth_client.post(url, data=payload, format="json")
    assert res.status_code == status.HTTP_201_CREATED
    
    # Verify response structure
    expected_fields = [
        'purchase_order_id', 'provider_name', 'product_id', 
        'product_name', 'image', 'product_sku', 'barcode_scanned',
        'quantity_ordered', 'purchase_unit', 'amount_miss', 'amount_boxes'
    ]
    for field in expected_fields:
        assert field in res.data, f"Missing field: {field}"
    
    # Verify specific values for extra products
    assert res.data['purchase_order_id'] == purchase_order.id
    assert res.data['product_id'] == extra_product.id
    assert res.data['product_name'] == extra_product.name
    assert res.data['quantity_ordered'] == 0  # Always 0 for extra products
    assert res.data['amount_miss'] == 0  # Always 0 for extra products
    assert res.data['amount_boxes'] == extra_product.amount_boxes
    
    # Verify database record
    received_product = ReceivedProduct.objects.filter(
        purchase_order=purchase_order,
        product=extra_product,
        is_not_in_order=True
    ).first()
    
    assert received_product is not None
    assert received_product.quantity_received == 3
    assert received_product.is_not_in_order is True
    assert received_product.reason_extra == "PROMOTIONAL"
    assert received_product.is_damaged is False
    assert received_product.notes == "Producto promocional del proveedor"


@pytest.mark.django_db
def test_received_extra_success_with_barcode(auth_client, purchase_order, extra_product_with_barcode, login_history):
    """Test registering extra product by barcode"""
    url = f"/api/received-products/{purchase_order.id}/received-extra/"
    payload = {
        "barcode": "9876543210",
        "quantity_received": 2,
        "is_damaged": True,
        "notes": "Producto dañado no ordenado",
        "reason": "ERROR"
    }
    
    res = auth_client.post(url, data=payload, format="json")
    assert res.status_code == status.HTTP_201_CREATED
    
    # Verify complete response structure
    expected_fields = [
        'purchase_order_id', 'provider_name', 'product_id', 
        'product_name', 'image', 'product_sku', 'barcode_scanned',
        'quantity_ordered', 'purchase_unit', 'amount_miss', 'amount_boxes'
    ]
    for field in expected_fields:
        assert field in res.data, f"Missing field: {field}"
    
    # Verify response values
    assert res.data['purchase_order_id'] == purchase_order.id
    assert res.data['provider_name'] == purchase_order.provider.name
    assert res.data['product_id'] == extra_product_with_barcode.id
    assert res.data['product_name'] == extra_product_with_barcode.name
    assert res.data['product_sku'] == extra_product_with_barcode.sku
    assert res.data['barcode_scanned'] == "9876543210"
    assert res.data['quantity_ordered'] == 0  # Always 0 for extra products
    assert res.data['purchase_unit'] == "units"  # Default unit
    assert res.data['amount_miss'] == 0  # Always 0 for extra products
    assert res.data['amount_boxes'] == extra_product_with_barcode.amount_boxes
    
    # Verify database record
    received_product = ReceivedProduct.objects.filter(
        purchase_order=purchase_order,
        product=extra_product_with_barcode,
        is_not_in_order=True
    ).first()
    
    assert received_product is not None
    assert received_product.quantity_received == 2
    assert received_product.barcode_scanned == "9876543210"
    assert received_product.is_damaged is True
    assert received_product.is_not_in_order is True
    assert received_product.reason_extra == "ERROR"
    assert received_product.notes == "Producto dañado no ordenado"
    assert received_product.market == login_history.market
    assert received_product.received_by == login_history.user


@pytest.mark.django_db
def test_received_extra_status_flags(auth_client, purchase_order, extra_product, login_history):
    """Test that status flags are set correctly for extra products"""
    url = f"/api/received-products/{purchase_order.id}/received-extra/"
    payload = {
        "product_id": extra_product.id,
        "quantity_received": 5,
        "reason": "OTHER"
    }
    
    res = auth_client.post(url, data=payload, format="json")
    assert res.status_code == status.HTTP_201_CREATED
    
    # Verify status flags in database
    received_product = ReceivedProduct.objects.filter(
        purchase_order=purchase_order,
        product=extra_product,
        is_not_in_order=True
    ).first()
    
    # For extra products with quantity > 0
    assert received_product.is_missing is False  # Never missing (not expected)
    assert received_product.is_over_received is True  # Always over (any quantity is excess)
    assert received_product.is_under_received is False  # Never under (doesn't apply)


@pytest.mark.django_db
def test_received_extra_zero_quantity(auth_client, purchase_order, extra_product, login_history):
    """Test extra product with zero quantity"""
    url = f"/api/received-products/{purchase_order.id}/received-extra/"
    payload = {
        "product_id": extra_product.id,
        "quantity_received": 0,
        "reason": "OTHER"
    }
    
    res = auth_client.post(url, data=payload, format="json")
    assert res.status_code == status.HTTP_201_CREATED
    
    # Verify response structure and values
    assert res.data['quantity_ordered'] == 0
    assert res.data['amount_miss'] == 0
    assert res.data['product_id'] == extra_product.id
    
    # Verify status flags for zero quantity
    received_product = ReceivedProduct.objects.filter(
        purchase_order=purchase_order,
        product=extra_product,
        is_not_in_order=True
    ).first()
    
    assert received_product is not None
    assert received_product.quantity_received == 0
    assert received_product.is_not_in_order is True
    assert received_product.reason_extra == "OTHER"
    assert received_product.is_missing is False  # Never missing for extra products
    assert received_product.is_over_received is False  # Zero quantity = no excess
    assert received_product.is_under_received is False  # Never under for extra products


@pytest.mark.django_db
def test_received_extra_validation_both_id_and_barcode(auth_client, purchase_order, extra_product, login_history):
    """Test validation error when providing both product_id and barcode"""
    url = f"/api/received-products/{purchase_order.id}/received-extra/"
    payload = {
        "product_id": extra_product.id,
        "barcode": "1234567890",
        "quantity_received": 1
    }
    
    res = auth_client.post(url, data=payload, format="json")
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert "exclusively" in res.data['detail']
    
    # Verify no record was created
    received_products = ReceivedProduct.objects.filter(
        purchase_order=purchase_order,
        product=extra_product,
        is_not_in_order=True
    )
    assert received_products.count() == 0


@pytest.mark.django_db
def test_received_extra_validation_no_id_or_barcode(auth_client, purchase_order, login_history):
    """Test validation error when providing neither product_id nor barcode"""
    url = f"/api/received-products/{purchase_order.id}/received-extra/"
    payload = {
        "quantity_received": 1
    }
    
    res = auth_client.post(url, data=payload, format="json")
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert "exclusively" in res.data['detail']
    
    # Verify no records were created
    received_products = ReceivedProduct.objects.filter(
        purchase_order=purchase_order,
        is_not_in_order=True
    )
    assert received_products.count() == 0


@pytest.mark.django_db
def test_received_extra_validation_invalid_quantity(auth_client, purchase_order, extra_product, login_history):
    """Test validation error for invalid quantity"""
    url = f"/api/received-products/{purchase_order.id}/received-extra/"
    payload = {
        "product_id": extra_product.id,
        "quantity_received": -1
    }
    
    res = auth_client.post(url, data=payload, format="json")
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert "greater than or equal to 0" in res.data['detail']
    
    # Test with non-integer quantity
    payload_invalid = {
        "product_id": extra_product.id,
        "quantity_received": "invalid"
    }
    
    res_invalid = auth_client.post(url, data=payload_invalid, format="json")
    assert res_invalid.status_code == status.HTTP_400_BAD_REQUEST
    assert "must be an integer" in res_invalid.data['detail']
    
    # Verify no records were created
    received_products = ReceivedProduct.objects.filter(
        purchase_order=purchase_order,
        product=extra_product,
        is_not_in_order=True
    )
    assert received_products.count() == 0


@pytest.mark.django_db
def test_received_extra_nonexistent_product(auth_client, purchase_order, login_history):
    """Test error when product doesn't exist"""
    url = f"/api/received-products/{purchase_order.id}/received-extra/"
    payload = {
        "product_id": 99999,  # Non-existent product
        "quantity_received": 1
    }
    
    res = auth_client.post(url, data=payload, format="json")
    assert res.status_code == status.HTTP_404_NOT_FOUND
    assert "not found" in res.data['detail']
    assert "99999" in res.data['detail']
    
    # Verify no records were created
    received_products = ReceivedProduct.objects.filter(
        purchase_order=purchase_order,
        is_not_in_order=True
    )
    assert received_products.count() == 0


@pytest.mark.django_db
def test_received_extra_nonexistent_barcode(auth_client, purchase_order, login_history):
    """Test error when barcode doesn't exist"""
    url = f"/api/received-products/{purchase_order.id}/received-extra/"
    payload = {
        "barcode": "NONEXISTENT",
        "quantity_received": 1
    }
    
    res = auth_client.post(url, data=payload, format="json")
    assert res.status_code == status.HTTP_404_NOT_FOUND
    assert "No product found with barcode" in res.data['detail']
    assert "NONEXISTENT" in res.data['detail']
    
    # Verify no records were created
    received_products = ReceivedProduct.objects.filter(
        purchase_order=purchase_order,
        is_not_in_order=True
    )
    assert received_products.count() == 0


@pytest.mark.django_db
def test_received_extra_creates_reception(auth_client, purchase_order, extra_product, login_history):
    """Test that reception is created/reused correctly"""
    # Ensure no reception exists initially
    assert Reception.objects.filter(
        purchase_order=purchase_order,
        market=login_history.market
    ).count() == 0
    
    url = f"/api/received-products/{purchase_order.id}/received-extra/"
    payload = {
        "product_id": extra_product.id,
        "quantity_received": 1,
        "reason": "OTHER"
    }
    
    res = auth_client.post(url, data=payload, format="json")
    assert res.status_code == status.HTTP_201_CREATED
    
    # Verify reception was created
    reception = Reception.objects.filter(
        purchase_order=purchase_order,
        market=login_history.market
    ).first()
    
    assert reception is not None
    assert reception.status == Reception.Status.DRAFT
    
    # Test that second call reuses the same reception
    payload2 = {
        "product_id": extra_product.id,
        "quantity_received": 2,
        "reason": "PROMOTIONAL"
    }
    
    res2 = auth_client.post(url, data=payload2, format="json")
    assert res2.status_code == status.HTTP_201_CREATED
    
    # Verify response structure for second call
    assert res2.data['purchase_order_id'] == purchase_order.id
    assert res2.data['product_id'] == extra_product.id
    assert res2.data['quantity_ordered'] == 0
    assert res2.data['amount_miss'] == 0
    
    # Should still be only one reception
    assert Reception.objects.filter(
        purchase_order=purchase_order,
        market=login_history.market
    ).count() == 1
    
    # But two received products
    received_products = ReceivedProduct.objects.filter(
        reception=reception,
        is_not_in_order=True
    )
    assert received_products.count() == 2
    
    # Verify both products have correct attributes
    for rp in received_products:
        assert rp.is_not_in_order is True
        assert rp.product == extra_product
        assert rp.market == login_history.market
        assert rp.received_by == login_history.user
        assert rp.reason_extra in ["OTHER", "PROMOTIONAL"]


@pytest.mark.django_db
def test_received_extra_no_market_history(auth_client, purchase_order, extra_product):
    """Test error when user has no login history (no market)"""
    url = f"/api/received-products/{purchase_order.id}/received-extra/"
    payload = {
        "product_id": extra_product.id,
        "quantity_received": 1
    }
    
    res = auth_client.post(url, data=payload, format="json")
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert "No market found" in res.data['detail']
    assert "no login history" in res.data['detail']
    
    # Verify no records were created
    received_products = ReceivedProduct.objects.filter(
        purchase_order=purchase_order,
        product=extra_product,
        is_not_in_order=True
    )
    assert received_products.count() == 0
    
    # Verify no reception was created
    receptions = Reception.objects.filter(purchase_order=purchase_order)
    assert receptions.count() == 0


@pytest.mark.django_db
def test_received_extra_nonexistent_purchase_order(auth_client, extra_product, login_history):
    """Test error when purchase order doesn't exist"""
    url = "/api/received-products/99999/received-extra/"
    payload = {
        "product_id": extra_product.id,
        "quantity_received": 1
    }
    
    res = auth_client.post(url, data=payload, format="json")
    assert res.status_code == status.HTTP_404_NOT_FOUND
    assert "not found" in res.data['detail']
    assert "99999" in res.data['detail']
    
    # Verify no records were created anywhere
    received_products = ReceivedProduct.objects.filter(
        product=extra_product,
        is_not_in_order=True
    )
    assert received_products.count() == 0
    
    # Verify no reception was created
    receptions = Reception.objects.all()
    assert receptions.count() == 0


@pytest.mark.django_db
def test_received_extra_appears_in_reception_retrieve(auth_client, purchase_order, extra_product, login_history):
    """Test that extra products appear correctly in reception retrieve endpoint"""
    # First register an extra product
    url = f"/api/received-products/{purchase_order.id}/received-extra/"
    payload = {
        "product_id": extra_product.id,
        "quantity_received": 3,
        "is_damaged": False,
        "notes": "Producto promocional",
        "reason": "PROMOTIONAL"
    }
    
    res = auth_client.post(url, data=payload, format="json")
    assert res.status_code == status.HTTP_201_CREATED
    
    # Get the reception
    reception = Reception.objects.filter(
        purchase_order=purchase_order,
        market=login_history.market
    ).first()
    assert reception is not None
    
    # Test reception retrieve endpoint
    reception_url = f"/api/receptions/{reception.id}/"
    reception_res = auth_client.get(reception_url)
    assert reception_res.status_code == status.HTTP_200_OK
    
    # Verify reception structure
    reception_data = reception_res.data
    assert reception_data['id'] == reception.id
    assert reception_data['purchase_order_id'] == purchase_order.id
    assert 'items' in reception_data
    
    # Find the extra product in items
    extra_items = [item for item in reception_data['items'] if item.get('is_not_in_order')]
    assert len(extra_items) == 1
    
    extra_item = extra_items[0]
    assert extra_item['product_id'] == extra_product.id
    assert extra_item['product_name'] == extra_product.name
    assert extra_item['quantity_received'] == 3
    assert extra_item['is_damaged'] is False
    assert extra_item['is_not_in_order'] is True
    assert extra_item['reason_extra'] == "PROMOTIONAL"
    assert extra_item['notes'] == "Producto promocional"
    
    # Verify status flags for extra product in reception
    assert extra_item['is_missing'] is False  # Never missing for extra products
    assert extra_item['is_over_received'] is True  # Always over for extra products with qty > 0
    assert extra_item['is_under_received'] is False  # Never under for extra products
