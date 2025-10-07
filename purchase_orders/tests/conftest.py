"""Configuración compartida de pytest para tests de purchase_orders."""

import pytest
from datetime import time
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from proveedores.models import Provider, Product
from market.models import Market, LoginHistory


@pytest.fixture
def api_client():
    """Cliente API sin autenticación."""
    return APIClient()


@pytest.fixture
def user(db):
    """Usuario de prueba."""
    User = get_user_model()
    return User.objects.create_user(username="tester", password="pass1234")


@pytest.fixture
def auth_client(api_client, user):
    """Cliente API autenticado con un usuario de prueba."""
    api_client.force_authenticate(user=user)
    return api_client


@pytest.fixture
def provider(db):
    """Proveedor de prueba con configuración básica."""
    return Provider.objects.create(
        name="Proveedor A",
        order_deadline_time=time(14, 30),
        order_available_weekdays=[0, 1, 2, 3, 4]  # Lun-Vie
    )


@pytest.fixture
def product1(provider):
    """Primer producto de prueba."""
    product = Product.objects.create(name="Producto 1", sku="SKU-1")
    product.providers.add(provider)
    return product


@pytest.fixture
def product2(provider):
    """Segundo producto de prueba."""
    product = Product.objects.create(name="Producto 2", sku="SKU-2")
    product.providers.add(provider)
    return product


# --- Fixtures para Market/LoginHistory ---

@pytest.fixture
def market(db):
    """Market base para asociar en LoginHistory."""
    return Market.objects.create(name="Mercado Test", latitude=41.387, longitude=2.170)


@pytest.fixture(autouse=True)
def user_login_history(user, market):
    """Asegura que el usuario autenticado tenga un LoginHistory reciente para derivar el market.

    Autouse para que todas las pruebas que creen órdenes encuentren el market.
    """
    LoginHistory.objects.create(
        user=user,
        market=market,
        latitude=market.latitude,
        longitude=market.longitude,
        event_type=LoginHistory.LOGIN,
    )
    return True
