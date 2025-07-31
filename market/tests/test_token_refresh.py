import pytest
from rest_framework.test import APIClient

from .factories import MarketFactory
from kachadigitalbcn.users.tests.factories import UserFactory


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user(db):
    """Create a user with known password so we can obtain tokens."""
    return UserFactory(password="password123")


def obtain_pair_token(client: APIClient, username: str, password: str, lat: float, lon: float):
    url = "/api/token/"
    payload = {
        "username": username,
        "password": password,
        "latitude": lat,
        "longitude": lon,
    }
    return client.post(url, payload, format="json")


def refresh_token(client: APIClient, refresh: str, lat: float, lon: float):
    url = "/api/token/refresh/"
    payload = {
        "refresh": refresh,
        "latitude": lat,
        "longitude": lon,
    }
    return client.post(url, payload, format="json")


def test_refresh_token_success(api_client, user):
    """La vista debe refrescar el token cuando el usuario está cerca del market."""
    market = MarketFactory()

    # Paso 1: obtener par de tokens válido
    obtain_response = obtain_pair_token(
        api_client, user.username, "password123", market.latitude, market.longitude
    )
    assert obtain_response.status_code == 200
    refresh = obtain_response.data["refresh"]

    # Paso 2: refrescar usando mismas coordenadas (distancia 0)
    refresh_response = refresh_token(api_client, refresh, market.latitude, market.longitude)
    assert refresh_response.status_code == 200
    data = refresh_response.data
    assert "access" in data
    assert data["market_name"] == market.name
    assert "login_time" in data


def test_refresh_token_denied_when_far(api_client, user):
    """Debe negar el refresco cuando el usuario está lejos del market."""
    market = MarketFactory()

    obtain_response = obtain_pair_token(
        api_client, user.username, "password123", market.latitude, market.longitude
    )
    assert obtain_response.status_code == 200
    refresh = obtain_response.data["refresh"]

    # Coordenadas lejanas (océano atlántico)
    refresh_response = refresh_token(api_client, refresh, 0.0, 0.0)
    assert refresh_response.status_code == 400
    assert "You are not near any market." in str(refresh_response.data)
