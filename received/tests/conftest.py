"""Shared test fixtures for received app."""

import pytest
from datetime import time
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from proveedores.models import Provider, Product, ProductBarcode
from purchase_orders.models import PurchaseOrder, PurchaseOrderItem


@pytest.fixture
def api_client():
    """API client without authentication."""
    return APIClient()


@pytest.fixture
def user(db):
    """Test user."""
    User = get_user_model()
    return User.objects.create_user(username="receiver", password="pass1234")


@pytest.fixture
def auth_client(api_client, user):
    """Authenticated API client with test user."""
    api_client.force_authenticate(user=user)
    return api_client


@pytest.fixture
def provider(db):
    """Test provider."""
    return Provider.objects.create(
        name="Test Provider",
        order_deadline_time=time(14, 30),
        order_available_weekdays=[0, 1, 2, 3, 4],
    )


@pytest.fixture
def product1(provider):
    """First test product."""
    product = Product.objects.create(
        name="Tomatoes",
        sku="TOM-001",
        amount_boxes=10,
    )
    product.providers.add(provider)
    return product


@pytest.fixture
def product2(provider):
    """Second test product."""
    product = Product.objects.create(
        name="Lettuce",
        sku="LET-001",
        amount_boxes=5,
    )
    product.providers.add(provider)
    return product


@pytest.fixture
def barcode1(product1):
    """Barcode for product1."""
    return ProductBarcode.objects.create(
        product=product1,
        code="1234567890123",
        type=ProductBarcode.BarcodeType.EAN13,
        is_primary=True,
    )


@pytest.fixture
def barcode2(product2):
    """Barcode for product2."""
    return ProductBarcode.objects.create(
        product=product2,
        code="9876543210987",
        type=ProductBarcode.BarcodeType.EAN13,
        is_primary=True,
    )


@pytest.fixture
def purchase_order(provider, user, product1, product2):
    """Test purchase order with items."""
    po = PurchaseOrder.objects.create(
        provider=provider,
        ordered_by=user,
        status=PurchaseOrder.Status.SHIPPED,
    )
    PurchaseOrderItem.objects.create(
        order=po,
        product=product1,
        quantity_units=10,
        purchase_unit="boxes",
    )
    PurchaseOrderItem.objects.create(
        order=po,
        product=product2,
        quantity_units=5,
        purchase_unit="boxes",
    )
    return po
