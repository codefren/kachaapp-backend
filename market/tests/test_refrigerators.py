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
    assert response.data[0]["morning_temperatures"] == []
    assert response.data[0]["night_temperatures"] == []


def test_today_temperature_returns_value(auth_client):
    record = TemperatureRecordFactory(temperature=2.5)
    fridge = record.refrigerator

    response = auth_client.get(f"/api/refrigerators/?market={fridge.market_id}")
    assert response.status_code == 200
    
    morning_temps = response.data[0]["morning_temperatures"]
    assert len(morning_temps) == 1
    assert morning_temps[0]["temperature"] == 2.5


def test_update_temperature_creates_record(auth_client):
    fridge = RefrigeratorFactory()
    url = f"/api/refrigerators/{fridge.id}/temperature/"
    resp = auth_client.put(url, {"temperature": 3.3}, format="json")
    assert resp.status_code == 200
    record = TemperatureRecord.objects.get(
        refrigerator=fridge, date=timezone.localdate(), period=TemperatureRecord.Period.MORNING
    )
    assert record.temperature == 3.3


def test_update_temperature_updates_existing_record(auth_client):
    record = TemperatureRecordFactory(temperature=4.0)
    fridge = record.refrigerator
    url = f"/api/refrigerators/{fridge.id}/temperature/"
    resp = auth_client.put(url, {"temperature": 1.8}, format="json")
    assert resp.status_code == 200
    record.refresh_from_db()
    assert record.temperature == 1.8


def test_update_temperature_with_night_period(auth_client):
    fridge = RefrigeratorFactory()
    url = f"/api/refrigerators/{fridge.id}/temperature/"
    resp = auth_client.put(url, {"temperature": 0.5, "period": TemperatureRecord.Period.NIGHT}, format="json")
    assert resp.status_code == 200
    record = TemperatureRecord.objects.get(
        refrigerator=fridge, date=timezone.localdate(), period=TemperatureRecord.Period.NIGHT
    )
    assert record.temperature == 0.5


def test_update_temperature_invalid_value_returns_400(auth_client):
    fridge = RefrigeratorFactory()
    url = f"/api/refrigerators/{fridge.id}/temperature/"
    # Fuera del rango permitido (> 10.0)
    resp = auth_client.put(url, {"temperature": 15.0}, format="json")
    assert resp.status_code == 400


def test_update_temperature_invalid_period_returns_400(auth_client):
    fridge = RefrigeratorFactory()
    url = f"/api/refrigerators/{fridge.id}/temperature/"
    resp = auth_client.put(url, {"temperature": 2.0, "period": "MIDDAY"}, format="json")
    assert resp.status_code == 400
