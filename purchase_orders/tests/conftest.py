"""Configuración compartida de pytest para tests de purchase_orders."""

import pytest
from datetime import time
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from proveedores.models import Provider, Product
from market.models import Market, LoginHistory
from kachadigitalbcn.users.models import Organization


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


# --- Fixtures para Multi-Market/Multi-Organization Testing ---

@pytest.fixture
def organization_a(db):
    """Organización A para testing de aislamiento."""
    return Organization.objects.create(
        name="Organización A",
        slug="org-a",
        is_active=True,
        contact_email="org-a@test.com",
        max_users=50,
        max_markets=100
    )


@pytest.fixture
def organization_b(db):
    """Organización B para testing de aislamiento."""
    return Organization.objects.create(
        name="Organización B",
        slug="org-b",
        is_active=True,
        contact_email="org-b@test.com",
        max_users=50,
        max_markets=100
    )


@pytest.fixture
def market_a(organization_a):
    """Market A perteneciente a organización A."""
    return Market.objects.create(
        name="Market A",
        organization=organization_a,
        latitude=41.387,
        longitude=2.170
    )


@pytest.fixture
def market_b(organization_b):
    """Market B perteneciente a organización B."""
    return Market.objects.create(
        name="Market B",
        organization=organization_b,
        latitude=41.400,
        longitude=2.180
    )


@pytest.fixture
def user_a(organization_a):
    """Usuario asignado a organización A."""
    User = get_user_model()
    return User.objects.create_user(
        username="user_a",
        password="pass1234",
        organization=organization_a
    )


@pytest.fixture
def user_b(organization_b):
    """Usuario asignado a organización B."""
    User = get_user_model()
    return User.objects.create_user(
        username="user_b",
        password="pass1234",
        organization=organization_b
    )


@pytest.fixture
def superuser(db):
    """Superusuario que puede ver todas las organizaciones."""
    User = get_user_model()
    return User.objects.create_superuser(
        username="admin",
        password="admin1234",
        email="admin@test.com"
    )


@pytest.fixture
def auth_client_a(user_a):
    """Cliente API autenticado con user_a (instancia independiente)."""
    client = APIClient()
    client.force_authenticate(user=user_a)
    return client


@pytest.fixture
def auth_client_b(user_b):
    """Cliente API autenticado con user_b (instancia independiente)."""
    client = APIClient()
    client.force_authenticate(user=user_b)
    return client


@pytest.fixture
def auth_client_superuser(superuser):
    """Cliente API autenticado con superuser (instancia independiente)."""
    client = APIClient()
    client.force_authenticate(user=superuser)
    return client


@pytest.fixture
def provider_a(organization_a):
    """Proveedor perteneciente a organización A."""
    return Provider.objects.create(
        name="Proveedor A",
        organization=organization_a,
        order_deadline_time=time(14, 30),
        order_available_weekdays=[0, 1, 2, 3, 4]  # Lun-Vie
    )


@pytest.fixture
def provider_b(organization_b):
    """Proveedor perteneciente a organización B."""
    return Provider.objects.create(
        name="Proveedor B",
        organization=organization_b,
        order_deadline_time=time(10, 0),
        order_available_weekdays=[1, 3, 5]  # Mar, Jue, Sáb
    )


@pytest.fixture
def product_a(provider_a):
    """Producto perteneciente a organización A (vía su proveedor)."""
    product = Product.objects.create(
        name="Producto A",
        sku="SKU-A"
    )
    product.providers.add(provider_a)
    return product


@pytest.fixture
def product_b(provider_b):
    """Producto perteneciente a organización B (vía su proveedor)."""
    product = Product.objects.create(
        name="Producto B",
        sku="SKU-B"
    )
    product.providers.add(provider_b)
    return product


@pytest.fixture
def login_history_a(user_a, market_a):
    """LoginHistory para user_a en market_a."""
    return LoginHistory.objects.create(
        user=user_a,
        market=market_a,
        latitude=market_a.latitude,
        longitude=market_a.longitude,
        event_type=LoginHistory.LOGIN
    )


@pytest.fixture
def login_history_b(user_b, market_b):
    """LoginHistory para user_b en market_b."""
    return LoginHistory.objects.create(
        user=user_b,
        market=market_b,
        latitude=market_b.latitude,
        longitude=market_b.longitude,
        event_type=LoginHistory.LOGIN
    )
