"""Tests para filtros de TemperatureRecord."""
import pytest
from django.utils import timezone
from datetime import timedelta

from market.models import TemperatureRecord
from market.tests.factories import TemperatureRecordFactory, MarketFactory, RefrigeratorFactory


@pytest.fixture
def auth_client(api_client, db):
    from market.tests.factories import UserFactory
    user = UserFactory()
    api_client.force_authenticate(user)
    return api_client


def test_filter_temperature_by_market(auth_client):
    """Verifica que se puedan filtrar temperaturas por market."""
    # Crear dos mercados diferentes
    market1 = MarketFactory()
    market2 = MarketFactory()
    
    # Crear refrigeradores en cada mercado
    fridge1 = RefrigeratorFactory(market=market1)
    fridge2 = RefrigeratorFactory(market=market2)
    
    # Crear temperaturas para cada refrigerador
    temp1 = TemperatureRecordFactory(refrigerator=fridge1, temperature=2.0)
    temp2 = TemperatureRecordFactory(refrigerator=fridge2, temperature=3.0)
    
    # Filtrar por market1
    response = auth_client.get(f"/api/temperature-records/?market={market1.id}")
    assert response.status_code == 200
    assert len(response.data) == 1
    assert response.data[0]["id"] == temp1.id
    
    # Filtrar por market2
    response = auth_client.get(f"/api/temperature-records/?market={market2.id}")
    assert response.status_code == 200
    assert len(response.data) == 1
    assert response.data[0]["id"] == temp2.id


def test_filter_temperature_by_date(auth_client):
    """Verifica que se puedan filtrar temperaturas por fecha exacta."""
    fridge = RefrigeratorFactory()
    today = timezone.localdate()
    yesterday = today - timedelta(days=1)
    
    # Crear temperaturas en diferentes fechas
    temp_today = TemperatureRecordFactory(
        refrigerator=fridge,
        date=today,
        temperature=2.0
    )
    temp_yesterday = TemperatureRecordFactory(
        refrigerator=fridge,
        date=yesterday,
        temperature=3.0
    )
    
    # Filtrar por fecha de hoy
    response = auth_client.get(f"/api/temperature-records/?date={today}")
    assert response.status_code == 200
    assert len(response.data) == 1
    assert response.data[0]["id"] == temp_today.id
    
    # Filtrar por fecha de ayer
    response = auth_client.get(f"/api/temperature-records/?date={yesterday}")
    assert response.status_code == 200
    assert len(response.data) == 1
    assert response.data[0]["id"] == temp_yesterday.id


def test_filter_temperature_by_date_range(auth_client):
    """Verifica que se puedan filtrar temperaturas por rango de fechas."""
    fridge = RefrigeratorFactory()
    today = timezone.localdate()
    
    # Crear temperaturas en 5 días consecutivos
    temps = []
    for i in range(5):
        date = today - timedelta(days=i)
        temp = TemperatureRecordFactory(
            refrigerator=fridge,
            date=date,
            temperature=float(i)
        )
        temps.append(temp)
    
    # Filtrar últimos 3 días (date_from)
    date_from = today - timedelta(days=2)
    response = auth_client.get(f"/api/temperature-records/?date_from={date_from}")
    assert response.status_code == 200
    assert len(response.data) == 3
    
    # Filtrar hasta hace 2 días (date_to)
    date_to = today - timedelta(days=2)
    response = auth_client.get(f"/api/temperature-records/?date_to={date_to}")
    assert response.status_code == 200
    assert len(response.data) == 3


def test_filter_temperature_by_period(auth_client):
    """Verifica que se puedan filtrar temperaturas por período (MORNING/NIGHT)."""
    fridge = RefrigeratorFactory()
    today = timezone.localdate()
    
    # Crear temperaturas de mañana y noche
    temp_morning = TemperatureRecordFactory(
        refrigerator=fridge,
        date=today,
        period=TemperatureRecord.Period.MORNING,
        temperature=2.0
    )
    temp_night = TemperatureRecordFactory(
        refrigerator=fridge,
        date=today,
        period=TemperatureRecord.Period.NIGHT,
        temperature=-3.0
    )
    
    # Filtrar solo mañana
    response = auth_client.get(f"/api/temperature-records/?period=MORNING")
    assert response.status_code == 200
    assert len(response.data) >= 1
    assert all(r["period"] == "MORNING" for r in response.data)
    
    # Filtrar solo noche
    response = auth_client.get(f"/api/temperature-records/?period=NIGHT")
    assert response.status_code == 200
    assert len(response.data) >= 1
    assert all(r["period"] == "NIGHT" for r in response.data)


def test_filter_temperature_by_refrigerator(auth_client):
    """Verifica que se puedan filtrar temperaturas por refrigerador."""
    fridge1 = RefrigeratorFactory()
    fridge2 = RefrigeratorFactory()
    
    # Crear temperaturas para cada refrigerador
    temp1 = TemperatureRecordFactory(refrigerator=fridge1, temperature=2.0)
    temp2 = TemperatureRecordFactory(refrigerator=fridge2, temperature=3.0)
    
    # Filtrar por fridge1
    response = auth_client.get(f"/api/temperature-records/?refrigerator={fridge1.id}")
    assert response.status_code == 200
    assert len(response.data) == 1
    assert response.data[0]["id"] == temp1.id
    
    # Filtrar por fridge2
    response = auth_client.get(f"/api/temperature-records/?refrigerator={fridge2.id}")
    assert response.status_code == 200
    assert len(response.data) == 1
    assert response.data[0]["id"] == temp2.id


def test_filter_temperature_combined_filters(auth_client):
    """Verifica que se puedan combinar múltiples filtros."""
    market = MarketFactory()
    fridge1 = RefrigeratorFactory(market=market)
    fridge2 = RefrigeratorFactory(market=market)
    today = timezone.localdate()
    
    # Crear temperaturas con diferentes características
    temp1 = TemperatureRecordFactory(
        refrigerator=fridge1,
        date=today,
        period=TemperatureRecord.Period.MORNING,
        temperature=2.0
    )
    temp2 = TemperatureRecordFactory(
        refrigerator=fridge2,
        date=today,
        period=TemperatureRecord.Period.NIGHT,
        temperature=-3.0
    )
    temp3 = TemperatureRecordFactory(
        refrigerator=fridge1,
        date=today - timedelta(days=1),
        period=TemperatureRecord.Period.MORNING,
        temperature=1.0
    )
    
    # Filtrar: market + date + period
    response = auth_client.get(
        f"/api/temperature-records/?market={market.id}&date={today}&period=MORNING"
    )
    assert response.status_code == 200
    assert len(response.data) == 1
    assert response.data[0]["id"] == temp1.id
    
    # Filtrar: refrigerator + period
    response = auth_client.get(
        f"/api/temperature-records/?refrigerator={fridge1.id}&period=MORNING"
    )
    assert response.status_code == 200
    assert len(response.data) == 2
    ids = [r["id"] for r in response.data]
    assert temp1.id in ids
    assert temp3.id in ids
