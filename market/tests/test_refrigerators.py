import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from market.models import TemperatureRecord
from .factories import RefrigeratorFactory, TemperatureRecordFactory
from kachadigitalbcn.users.tests.factories import UserFactory


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def auth_client(api_client, db):
    user = UserFactory()
    api_client.force_authenticate(user)
    return api_client


def test_today_temperature_zero_when_no_record(auth_client):
    fridge = RefrigeratorFactory()

    response = auth_client.get(f"/api/refrigerators/?market={fridge.market_id}")
    assert response.status_code == 200
    assert response.data[0]["today_temperature"] == 0.0


def test_today_temperature_returns_value(auth_client):
    record = TemperatureRecordFactory(temperature=2.5)
    fridge = record.refrigerator

    response = auth_client.get(f"/api/refrigerators/?market={fridge.market_id}")
    assert response.status_code == 200
    assert response.data[0]["today_temperature"] == 2.5


def test_update_temperature_creates_record(auth_client):
    fridge = RefrigeratorFactory()
    url = f"/api/refrigerators/{fridge.id}/temperature/"
    resp = auth_client.put(url, {"temperature": 3.3}, format="json")
    assert resp.status_code == 200
    record = TemperatureRecord.objects.get(refrigerator=fridge, date=timezone.localdate())
    assert record.temperature == 3.3


def test_update_temperature_updates_existing_record(auth_client):
    record = TemperatureRecordFactory(temperature=4.0)
    fridge = record.refrigerator
    url = f"/api/refrigerators/{fridge.id}/temperature/"
    resp = auth_client.put(url, {"temperature": 1.8}, format="json")
    assert resp.status_code == 200
    record.refresh_from_db()
    assert record.temperature == 1.8
