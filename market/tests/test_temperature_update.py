"""Tests de actualización de temperaturas de refrigeradores."""

import pytest
from django.utils import timezone

from market.models import TemperatureRecord
from market.tests.factories import RefrigeratorFactory, TemperatureRecordFactory


def test_update_temperature_creates_record(auth_client):
    """Verifica que al actualizar la temperatura se cree un nuevo registro."""
    fridge = RefrigeratorFactory()
    url = f"/api/refrigerators/{fridge.id}/temperature/"
    resp = auth_client.put(url, {"temperature": 3.3}, format="json")
    assert resp.status_code == 200
    record = TemperatureRecord.objects.get(
        refrigerator=fridge,
        date=timezone.localdate(),
        period=TemperatureRecord.Period.MORNING,
    )
    assert record.temperature == 3.3


def test_update_temperature_updates_existing_record(auth_client):
    """Verifica que al actualizar una temperatura existente se modifique el registro."""
    record = TemperatureRecordFactory(temperature=4.0)
    fridge = record.refrigerator
    url = f"/api/refrigerators/{fridge.id}/temperature/"
    resp = auth_client.put(url, {"temperature": 1.8}, format="json")
    assert resp.status_code == 200
    record.refresh_from_db()
    assert record.temperature == 1.8


def test_update_temperature_with_night_period(auth_client):
    """Verifica que se pueda actualizar la temperatura con período NIGHT."""
    fridge = RefrigeratorFactory()
    url = f"/api/refrigerators/{fridge.id}/temperature/"
    resp = auth_client.put(
        url,
        {"temperature": 0.5, "period": TemperatureRecord.Period.NIGHT},
        format="json",
    )
    assert resp.status_code == 200
    record = TemperatureRecord.objects.get(
        refrigerator=fridge,
        date=timezone.localdate(),
        period=TemperatureRecord.Period.NIGHT,
    )
    assert record.temperature == 0.5


def test_update_temperature_invalid_value_returns_400(auth_client):
    """Verifica que un valor de temperatura inválido retorne 400."""
    fridge = RefrigeratorFactory()
    url = f"/api/refrigerators/{fridge.id}/temperature/"
    # Fuera del rango permitido (> 10.0)
    resp = auth_client.put(url, {"temperature": 15.0}, format="json")
    assert resp.status_code == 400


def test_update_temperature_invalid_period_returns_400(auth_client):
    """Verifica que un período inválido retorne 400."""
    fridge = RefrigeratorFactory()
    url = f"/api/refrigerators/{fridge.id}/temperature/"
    resp = auth_client.put(url, {"temperature": 2.0, "period": "MIDDAY"}, format="json")
    assert resp.status_code == 400
