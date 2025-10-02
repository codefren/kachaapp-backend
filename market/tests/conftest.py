"""Configuración compartida de pytest para tests de market."""

import pytest
from rest_framework.test import APIClient

from kachadigitalbcn.users.tests.factories import UserFactory


@pytest.fixture
def api_client():
    """Cliente API sin autenticación."""
    return APIClient()


@pytest.fixture
def auth_client(api_client, db):
    """Cliente API autenticado con un usuario de prueba."""
    user = UserFactory()
    api_client.force_authenticate(user)
    return api_client
