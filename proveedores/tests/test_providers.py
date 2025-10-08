"""Tests para el modelo Provider y su API."""

import pytest
from datetime import time, datetime
import re
from rest_framework import status

from purchase_orders.models import PurchaseOrder
from proveedores.models import Provider
from market.models import Market, LoginHistory


def test_list_providers(auth_client, provider, user):
    """Verifica que se pueda listar proveedores."""
    # Crear LoginHistory requerido para listar proveedores
    market = Market.objects.create(name="Test Market", latitude=41.4, longitude=2.1)
    LoginHistory.objects.create(
        user=user,
        market=market,
        latitude=market.latitude,
        longitude=market.longitude,
        event_type=LoginHistory.LOGIN,
    )
    url = "/api/providers/"
    res = auth_client.get(url)
    assert res.status_code == status.HTTP_200_OK
    assert len(res.data) >= 1
    assert "name" in res.data[0]
    # Aseguramos campos actuales del serializer
    assert "has_received_orders" in res.data[0]
    assert "last_shipped_order_id" in res.data[0]


def test_provider_has_received_orders_flag(auth_client, provider, user):
    """Test que el campo has_received_orders funcione correctamente en ProviderSerializer."""
    # Inicialmente, el proveedor no debe tener órdenes PLACED o DRAFT
    url = f"/api/providers/{provider.id}/"
    res = auth_client.get(url)
    assert res.status_code == status.HTTP_200_OK
    has_received = res.data.get("has_received_orders")
    assert isinstance(has_received, dict)
    assert has_received["status"] is None
    assert has_received["order_id"] is None

    # Crear una orden en estado PLACED
    po_placed = PurchaseOrder.objects.create(
        provider=provider, 
        ordered_by=user, 
        status=PurchaseOrder.Status.PLACED
    )
    
    # Ahora debe tener información de la orden PLACED
    res2 = auth_client.get(url)
    assert res2.status_code == status.HTTP_200_OK
    has_received2 = res2.data.get("has_received_orders")
    assert isinstance(has_received2, dict)
    assert has_received2["status"] == PurchaseOrder.Status.PLACED
    assert has_received2["order_id"] == po_placed.id

    # Crear una orden en estado DRAFT (más reciente)
    po_draft = PurchaseOrder.objects.create(
        provider=provider, 
        ordered_by=user, 
        status=PurchaseOrder.Status.DRAFT
    )
    
    # Ahora debe tener información de la orden DRAFT (la más reciente)
    res3 = auth_client.get(url)
    assert res3.status_code == status.HTTP_200_OK
    has_received3 = res3.data.get("has_received_orders")
    assert isinstance(has_received3, dict)
    assert has_received3["status"] == PurchaseOrder.Status.DRAFT
    assert has_received3["order_id"] == po_draft.id

    # Verificar también en la lista de proveedores (debe devolver la más reciente: DRAFT)
    # Crear LoginHistory para permitir listar proveedores
    market = Market.objects.create(name="Test Market", latitude=41.4, longitude=2.1)
    LoginHistory.objects.create(
        user=user,
        market=market,
        latitude=market.latitude,
        longitude=market.longitude,
        event_type=LoginHistory.LOGIN,
    )
    list_url = "/api/providers/"
    res_list = auth_client.get(list_url)
    assert res_list.status_code == status.HTTP_200_OK
    provider_data = next((p for p in res_list.data if p["id"] == provider.id), None)
    assert provider_data is not None
    provider_has_received = provider_data.get("has_received_orders")
    assert isinstance(provider_has_received, dict)
    assert provider_has_received["status"] == PurchaseOrder.Status.DRAFT
    assert provider_has_received["order_id"] == po_draft.id


def test_provider_order_schedule_fields(auth_client, provider, user):
    """Test que verifica que los campos de horario de pedidos se devuelven correctamente."""
    # Configurar proveedor con días laborales (Lun-Vie) y hora límite 14:30
    provider.order_available_weekdays = [0, 1, 2, 3, 4]  # Lun-Vie
    provider.order_deadline_time = time(14, 30)
    provider.save()

    url = f"/api/providers/{provider.id}/"
    res = auth_client.get(url)

    assert res.status_code == status.HTTP_200_OK

    # Verificar que los campos están presentes en la respuesta
    assert "order_deadline_time" in res.data
    assert "order_available_weekdays" in res.data

    # Verificar valores correctos
    assert res.data["order_deadline_time"] == "14:30:00"
    assert res.data["order_available_weekdays"] == [0, 1, 2, 3, 4]

    # Verificar que el campo order_available_dates está presente
    assert "order_available_dates" in res.data
    assert isinstance(res.data["order_available_dates"], list)

    # Verificar también en la lista de proveedores
    # Crear LoginHistory para permitir listar proveedores
    market = Market.objects.create(name="Test Market", latitude=41.4, longitude=2.1)
    LoginHistory.objects.create(
        user=user,
        market=market,
        latitude=market.latitude,
        longitude=market.longitude,
        event_type=LoginHistory.LOGIN,
    )
    list_url = "/api/providers/"
    res_list = auth_client.get(list_url)
    assert res_list.status_code == status.HTTP_200_OK

    provider_data = next((p for p in res_list.data if p["id"] == provider.id), None)
    assert provider_data is not None
    assert provider_data["order_deadline_time"] == "14:30:00"
    assert provider_data["order_available_weekdays"] == [0, 1, 2, 3, 4]


def test_provider_order_schedule_required_fields(auth_client, provider):
    """Test que verifica que ambos campos de horario son requeridos y se devuelven correctamente."""
    # Configurar proveedor con todos los campos requeridos
    provider.order_available_weekdays = [1, 2, 3]  # Mar-Jue
    provider.order_deadline_time = time(16, 0)  # 16:00
    provider.save()

    url = f"/api/providers/{provider.id}/"
    res = auth_client.get(url)

    assert res.status_code == status.HTTP_200_OK

    # Verificar que ambos campos están presentes y son requeridos
    assert res.data["order_deadline_time"] == "16:00:00"
    assert res.data["order_available_weekdays"] == [1, 2, 3]

    # Verificar que no pueden ser nulos
    assert res.data["order_deadline_time"] is not None
    assert res.data["order_available_weekdays"] is not None


def test_provider_order_available_dates_format(auth_client, provider):
    """Test que verifica el formato correcto de las fechas en order_available_dates."""
    # Configurar proveedor con días específicos
    provider.order_available_weekdays = [1, 3, 5]  # Martes, Jueves, Sábado
    provider.order_deadline_time = time(15, 0)
    provider.save()

    url = f"/api/providers/{provider.id}/"
    res = auth_client.get(url)

    assert res.status_code == status.HTTP_200_OK

    # Verificar que el campo existe y es una lista
    assert "order_available_dates" in res.data
    dates = res.data["order_available_dates"]
    assert isinstance(dates, list)

    # Patrón regex para formato "Día DD/MM/YYYY"
    date_pattern = re.compile(r'^(Lunes|Martes|Miércoles|Jueves|Viernes|Sábado|Domingo) \d{2}/\d{2}/\d{4}$')

    # Verificar que todas las fechas tienen el formato correcto
    for date_str in dates:
        assert isinstance(date_str, str)
        assert date_pattern.match(date_str), \
            f"Fecha '{date_str}' no tiene el formato 'Día DD/MM/YYYY'"

    # Verificar que las fechas están ordenadas cronológicamente
    if len(dates) > 1:
        # Extraer solo las fechas para comparar cronológicamente
        date_objects = []
        for date_str in dates:
            date_part = date_str.split(' ')[1]  # Obtener "DD/MM/YYYY"
            date_obj = datetime.strptime(date_part, '%d/%m/%Y').date()
            date_objects.append(date_obj)

        for i in range(1, len(date_objects)):
            assert date_objects[i] > date_objects[i-1], \
                "Las fechas deben estar ordenadas cronológicamente"

    # Verificar que no hay fechas duplicadas
    assert len(dates) == len(set(dates)), \
        "No debe haber fechas duplicadas"

    # Verificar que las fechas corresponden a los días configurados
    for date_str in dates:
        # Extraer solo la parte de la fecha del string "Día DD/MM/YYYY"
        date_part = date_str.split(' ')[1]  # Obtener "DD/MM/YYYY"
        date_obj = datetime.strptime(date_part, '%d/%m/%Y').date()
        weekday = date_obj.weekday()
        assert weekday in provider.order_available_weekdays, \
            f"La fecha {date_str} (día {weekday}) no está en los días configurados"
        
        # Verificar que el nombre del día coincide con el weekday
        day_name = date_str.split(' ')[0]  # Obtener "Día"
        expected_names = {
            0: 'Lunes', 1: 'Martes', 2: 'Miércoles', 3: 'Jueves',
            4: 'Viernes', 5: 'Sábado', 6: 'Domingo'
        }
        assert day_name == expected_names[weekday], \
            f"El nombre del día '{day_name}' no coincide con el weekday {weekday}"
