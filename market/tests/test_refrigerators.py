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
    """Verifica que morning_temperature y night_temperature sean None cuando no hay registros del día actual."""
    fridge = RefrigeratorFactory()

    response = auth_client.get(f"/api/refrigerators/?market={fridge.market_id}")

    assert response.status_code == 200
    assert response.data[0]["morning_temperature"] is None
    assert response.data[0]["night_temperature"] is None


def test_today_temperature_returns_value(auth_client):
    """Verifica que morning_temperature y night_temperature devuelvan los objetos del día actual para múltiples refrigeradores."""
    from market.tests.factories import MarketFactory

    # Crear un mercado compartido
    market = MarketFactory()
    today = timezone.localdate()

    # Refrigerador 1: Con ambas temperaturas
    morning_record1 = TemperatureRecordFactory(
        temperature=2.5, period=TemperatureRecord.Period.MORNING, date=today
    )
    fridge1 = morning_record1.refrigerator
    fridge1.market = market
    fridge1.save()

    TemperatureRecordFactory(
        refrigerator=fridge1,
        date=today,
        temperature=-3.5,
        period=TemperatureRecord.Period.NIGHT,
    )

    # Refrigerador 2: Solo temperatura de mañana
    morning_record2 = TemperatureRecordFactory(
        temperature=1.0, period=TemperatureRecord.Period.MORNING, date=today
    )
    fridge2 = morning_record2.refrigerator
    fridge2.market = market
    fridge2.save()

    # Refrigerador 3: Solo temperatura de noche
    from market.tests.factories import RefrigeratorFactory

    fridge3 = RefrigeratorFactory(market=market)
    TemperatureRecordFactory(
        refrigerator=fridge3,
        date=today,
        temperature=-5.0,
        period=TemperatureRecord.Period.NIGHT,
    )

    response = auth_client.get(f"/api/refrigerators/?market={market.id}")
    assert response.status_code == 200
    assert (
        len(response.data) == 3
    ), f"Esperaba 3 refrigeradores, obtuvo {len(response.data)}"

    # Ordenar por id para verificación consistente
    fridges_data = sorted(response.data, key=lambda x: x["id"])

    # Verificar Refrigerador 1: Ambas temperaturas
    fridge1_data = next(f for f in fridges_data if f["id"] == fridge1.id)
    morning_temp = fridge1_data["morning_temperature"]
    assert morning_temp is not None
    assert morning_temp["temperature"] == 2.5
    assert morning_temp["period"] == "MORNING"
    assert "id" in morning_temp
    assert "date" in morning_temp
    assert "is_critical" in morning_temp
    assert "recorded_at" in morning_temp

    night_temp = fridge1_data["night_temperature"]
    assert night_temp is not None
    assert night_temp["temperature"] == -3.5
    assert night_temp["period"] == "NIGHT"

    # Verificar Refrigerador 2: Solo mañana
    fridge2_data = next(f for f in fridges_data if f["id"] == fridge2.id)
    assert fridge2_data["morning_temperature"] is not None
    assert fridge2_data["morning_temperature"]["temperature"] == 1.0
    assert fridge2_data["night_temperature"] is None

    # Verificar Refrigerador 3: Solo noche
    fridge3_data = next(f for f in fridges_data if f["id"] == fridge3.id)
    assert fridge3_data["morning_temperature"] is None
    assert fridge3_data["night_temperature"] is not None
    assert fridge3_data["night_temperature"]["temperature"] == -5.0


def test_update_temperature_creates_record(auth_client):
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


def test_refrigerator_with_both_temperatures(auth_client):
    """Verifica que se devuelvan ambas temperaturas (mañana y noche) del día actual."""
    fridge = RefrigeratorFactory()
    today = timezone.localdate()

    # Crear temperatura de mañana
    TemperatureRecordFactory(
        refrigerator=fridge,
        date=today,
        temperature=-2.5,
        period=TemperatureRecord.Period.MORNING,
    )

    # Crear temperatura de noche
    TemperatureRecordFactory(
        refrigerator=fridge,
        date=today,
        temperature=-3.0,
        period=TemperatureRecord.Period.NIGHT,
    )

    response = auth_client.get(f"/api/refrigerators/{fridge.id}/")
    assert response.status_code == 200

    # Verificar morning_temperature
    morning_temp = response.data["morning_temperature"]
    assert morning_temp is not None
    assert morning_temp["temperature"] == -2.5
    assert morning_temp["period"] == "MORNING"

    # Verificar night_temperature
    night_temp = response.data["night_temperature"]
    assert night_temp is not None
    assert night_temp["temperature"] == -3.0
    assert night_temp["period"] == "NIGHT"


def test_refrigerator_with_only_morning_temperature(auth_client):
    """Verifica que solo morning_temperature tenga datos y night_temperature sea None."""
    fridge = RefrigeratorFactory()
    today = timezone.localdate()

    # Crear solo temperatura de mañana
    TemperatureRecordFactory(
        refrigerator=fridge,
        date=today,
        temperature=1.5,
        period=TemperatureRecord.Period.MORNING,
    )

    response = auth_client.get(f"/api/refrigerators/{fridge.id}/")
    assert response.status_code == 200

    # Verificar morning_temperature existe
    morning_temp = response.data["morning_temperature"]
    assert morning_temp is not None
    assert morning_temp["temperature"] == 1.5

    # Verificar night_temperature es None
    night_temp = response.data["night_temperature"]
    assert night_temp is None


def test_refrigerator_with_only_night_temperature(auth_client):
    """Verifica que solo night_temperature tenga datos y morning_temperature sea None."""
    fridge = RefrigeratorFactory()
    today = timezone.localdate()

    # Crear solo temperatura de noche
    TemperatureRecordFactory(
        refrigerator=fridge,
        date=today,
        temperature=-1.0,
        period=TemperatureRecord.Period.NIGHT,
    )

    response = auth_client.get(f"/api/refrigerators/{fridge.id}/")
    assert response.status_code == 200

    # Verificar morning_temperature es None
    morning_temp = response.data["morning_temperature"]
    assert morning_temp is None

    # Verificar night_temperature existe
    night_temp = response.data["night_temperature"]
    assert night_temp is not None
    assert night_temp["temperature"] == -1.0


def test_refrigerator_list_structure(auth_client):
    """Verifica que la lista de refrigeradores tenga la estructura correcta."""
    fridge = RefrigeratorFactory()

    response = auth_client.get(f"/api/refrigerators/?market={fridge.market_id}")
    assert response.status_code == 200
    assert len(response.data) >= 1

    # Verificar estructura de cada refrigerador
    refrigerator_data = response.data[0]
    expected_fields = [
        "id",
        "name",
        "market",
        "morning_temperature",
        "night_temperature",
        "created_at",
    ]

    for field in expected_fields:
        assert field in refrigerator_data, f"Falta el campo {field}"


def test_temperature_record_structure(auth_client):
    """Verifica que los objetos de temperatura tengan todos los campos requeridos."""
    fridge = RefrigeratorFactory()
    today = timezone.localdate()

    TemperatureRecordFactory(
        refrigerator=fridge,
        date=today,
        temperature=2.0,
        period=TemperatureRecord.Period.MORNING,
    )

    response = auth_client.get(f"/api/refrigerators/{fridge.id}/")
    assert response.status_code == 200

    morning_temp = response.data["morning_temperature"]
    expected_temp_fields = [
        "id",
        "date",
        "temperature",
        "period",
        "is_critical",
        "recorded_at",
    ]

    for field in expected_temp_fields:
        assert field in morning_temp, f"Falta el campo {field} en temperature record"
