"""Tests de acciones personalizadas de Purchase Orders (by-day, has-ordered-today, last-shipped, received-products)."""

import pytest
from datetime import timedelta, time
from django.utils import timezone
from django.contrib.auth import get_user_model
from rest_framework import status

from purchase_orders.models import PurchaseOrder, PurchaseOrderItem
from proveedores.models import Provider, ProductBarcode


def test_has_ordered_today(auth_client, provider, user, product1):
    """Verifica la acción has-ordered-today."""
    url = "/api/purchase-orders/has-ordered-today/"
    # Inicialmente, no debe haber órdenes hoy
    res1 = auth_client.get(url)
    assert res1.status_code == status.HTTP_200_OK
    assert not res1.data.get("has_ordered_today")

    # Crear una orden hoy
    create_url = "/api/purchase-orders/"
    payload = {
        "provider": provider.id,
        "ordered_by": user.id,
        "status": "PLACED",
        "items": [
            {"product": product1.id, "quantity_units": 1, "unit_type": "boxes", "amount_boxes": 1},
        ],
    }
    res_create = auth_client.post(create_url, data=payload, format="json")
    assert res_create.status_code == status.HTTP_201_CREATED

    # Ahora debe retornar true
    res2 = auth_client.get(url)
    assert res2.status_code == status.HTTP_200_OK
    assert res2.data.get("has_ordered_today")


def test_has_ordered_today_with_provider_filter(auth_client, provider, user, product1):
    """Verifica has-ordered-today con filtro por proveedor."""
    base_url = "/api/purchase-orders/has-ordered-today/"
    # Crear otro proveedor
    other_provider = Provider.objects.create(
        name="Proveedor B",
        order_deadline_time=time(16, 0),
        order_available_weekdays=[0, 1, 2, 3, 4]
    )
    # Crear una orden hoy con provider principal
    create_url = "/api/purchase-orders/"
    payload = {
        "provider": provider.id,
        "ordered_by": user.id,
        "status": "PLACED",
        "items": [
            {"product": product1.id, "quantity_units": 1, "unit_type": "units"},
        ],
    }
    res_create = auth_client.post(create_url, data=payload, format="json")
    assert res_create.status_code == status.HTTP_201_CREATED

    # Filtro por provider correcto -> true
    res_yes = auth_client.get(f"{base_url}?provider={provider.id}")
    assert res_yes.status_code == status.HTTP_200_OK
    assert res_yes.data.get("has_ordered_today")

    # Filtro por provider distinto -> false
    res_no = auth_client.get(f"{base_url}?provider={other_provider.id}")
    assert res_no.status_code == status.HTTP_200_OK
    assert not res_no.data.get("has_ordered_today")


def test_has_ordered_today_with_invalid_provider_param(auth_client):
    """Verifica que un provider inválido retorne 400."""
    url = "/api/purchase-orders/has-ordered-today/?provider=abc"
    res = auth_client.get(url)
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert "detail" in res.data


def test_filter_purchase_orders_by_date(auth_client, provider, user, product1, product2):
    """Verifica que se puedan filtrar órdenes por fecha."""
    # Crear 2 órdenes
    url = "/api/purchase-orders/"
    payload1 = {
        "provider": provider.id,
        "ordered_by": user.id,
        "status": "PLACED",
        "items": [
            {"product": product1.id, "quantity_units": 1, "unit_type": "boxes", "amount_boxes": 1},
        ],
    }
    res1 = auth_client.post(url, data=payload1, format="json")
    assert res1.status_code == status.HTTP_201_CREATED

    payload2 = {
        "provider": provider.id,
        "ordered_by": user.id,
        "status": "PLACED",
        "items": [
            {"product": product2.id, "quantity_units": 1, "unit_type": "boxes", "amount_boxes": 1},
        ],
    }
    res2 = auth_client.post(url, data=payload2, format="json")
    assert res2.status_code == status.HTTP_201_CREATED

    # Mover la segunda orden a "ayer" modificando created_at
    po2_id = res2.data["id"]
    yesterday = timezone.now() - timedelta(days=1)
    PurchaseOrder.objects.filter(id=po2_id).update(created_at=yesterday)

    # Consultar por hoy con la acción by-day: debe devolver un objeto (la orden de hoy)
    today_str = timezone.now().date().isoformat()
    res_today = auth_client.get(f"/api/purchase-orders/by-day/?date={today_str}")
    assert res_today.status_code == status.HTTP_200_OK
    assert isinstance(res_today.data, dict)

    # Consultar por ayer con la acción by-day: debe devolver un objeto (la orden movida a ayer)
    yesterday_str = (timezone.now() - timedelta(days=1)).date().isoformat()
    res_yest = auth_client.get(f"/api/purchase-orders/by-day/?date={yesterday_str}")
    assert res_yest.status_code == status.HTTP_200_OK
    assert isinstance(res_yest.data, dict)


def test_by_day_no_results_returns_message(auth_client):
    """Verifica que by-day sin resultados devuelva un mensaje."""
    future_day = (timezone.now() + timedelta(days=15)).date().isoformat()
    res = auth_client.get(f"/api/purchase-orders/by-day/?date={future_day}")
    assert res.status_code == status.HTTP_200_OK
    assert isinstance(res.data, dict)
    assert res.data.get("detail") == "No existen órdenes para el día seleccionado."


def test_by_day_missing_date_returns_400(auth_client):
    """Verifica que by-day sin parámetro date retorne 400."""
    res = auth_client.get("/api/purchase-orders/by-day/")
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert "detail" in res.data


def test_by_day_invalid_date_returns_400(auth_client):
    """Verifica que by-day con fecha inválida retorne 400."""
    res = auth_client.get("/api/purchase-orders/by-day/?date=2025-13-40")
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert "detail" in res.data


def test_by_day_with_result_returns_single_object(auth_client, provider, user, product1):
    """Verifica que by-day con resultado devuelva un objeto."""
    # Crear una orden hoy
    url = "/api/purchase-orders/"
    payload = {
        "provider": provider.id,
        "ordered_by": user.id,
        "status": "PLACED",
        "items": [
            {"product": product1.id, "quantity_units": 2, "unit_type": "boxes", "amount_boxes": 2},
        ],
    }
    res_create = auth_client.post(url, data=payload, format="json")
    assert res_create.status_code == status.HTTP_201_CREATED

    day = timezone.now().date().isoformat()
    res = auth_client.get(f"/api/purchase-orders/by-day/?date={day}")
    assert res.status_code == status.HTTP_200_OK
    # Debe ser un objeto, no lista
    assert isinstance(res.data, dict)
    assert "id" in res.data


def test_list_purchase_orders_with_date_no_results_returns_message(auth_client):
    """Verifica que by-day sin resultados en una fecha futura devuelva mensaje."""
    # Asegurarnos de que no haya órdenes en una fecha futura
    future_day = (timezone.now() + timedelta(days=30)).date().isoformat()

    url = f"/api/purchase-orders/by-day/?date={future_day}"
    res = auth_client.get(url)
    assert res.status_code == status.HTTP_200_OK
    # Debe devolver un objeto con 'detail' y no una lista vacía
    assert isinstance(res.data, dict)
    assert "detail" in res.data
    assert res.data["detail"] == "No existen órdenes para el día seleccionado."


def test_purchase_order_queryset_for_by_day_and_provider(auth_client, provider, user):
    """Verifica el queryset de by-day con filtro por proveedor."""
    # Crear otro proveedor
    other_provider = Provider.objects.create(
        name="Proveedor C",
        order_deadline_time=time(17, 0),
        order_available_weekdays=[1, 2, 3]
    )

    # Crear dos órdenes hoy: una para provider principal (más antigua) y otra para el otro provider (más reciente)
    po1 = PurchaseOrder.objects.create(provider=provider, ordered_by=user, status="PLACED")
    po2 = PurchaseOrder.objects.create(provider=other_provider, ordered_by=user, status="PLACED")

    # Ajustar created_at para que po1 sea más antigua que po2
    older = timezone.now() - timedelta(hours=1)
    PurchaseOrder.objects.filter(id=po1.id).update(created_at=older)

    day = timezone.now().date().isoformat()

    # Filtro por provider principal -> debe devolver po1
    res_main = auth_client.get(f"/api/purchase-orders/by-day/?date={day}&provider={provider.id}")
    assert res_main.status_code == status.HTTP_200_OK
    assert isinstance(res_main.data, dict)
    assert res_main.data.get("provider") == provider.id

    # Filtro por otro provider -> debe devolver po2 (la más reciente de ese provider)
    res_other = auth_client.get(f"/api/purchase-orders/by-day/?date={day}&provider={other_provider.id}")
    assert res_other.status_code == status.HTTP_200_OK
    assert isinstance(res_other.data, dict)
    assert res_other.data.get("provider") == other_provider.id

    # provider inválido -> 400
    res_bad = auth_client.get(f"/api/purchase-orders/by-day/?date={day}&provider=abc")
    assert res_bad.status_code == status.HTTP_400_BAD_REQUEST
    assert "detail" in res_bad.data


def test_last_shipped_returns_latest_for_authenticated_user(auth_client, provider, user):
    """Verifica que last-shipped devuelva la orden SHIPPED más reciente."""
    # Crear dos órdenes SHIPPED para el usuario autenticado
    po1 = PurchaseOrder.objects.create(provider=provider, ordered_by=user, status="SHIPPED")
    po2 = PurchaseOrder.objects.create(provider=provider, ordered_by=user, status="SHIPPED")

    # Forzar que po2 sea la más reciente por updated_at
    newer = timezone.now()
    older = newer - timedelta(minutes=5)
    PurchaseOrder.objects.filter(id=po1.id).update(updated_at=older)
    PurchaseOrder.objects.filter(id=po2.id).update(updated_at=newer)

    url = "/api/purchase-orders/last-shipped/"
    res = auth_client.get(url)
    assert res.status_code == status.HTTP_200_OK
    assert isinstance(res.data, dict)
    assert res.data.get("id") == po2.id


def test_last_shipped_filters_by_provider(auth_client, provider, user):
    """Verifica que last-shipped filtre por proveedor."""
    other_provider = Provider.objects.create(
        name="Proveedor Z",
        order_deadline_time=time(18, 0),
        order_available_weekdays=[0, 2, 4]
    )

    # Órdenes SHIPPED para distintos proveedores
    po_main = PurchaseOrder.objects.create(provider=provider, ordered_by=user, status="SHIPPED")
    po_other = PurchaseOrder.objects.create(provider=other_provider, ordered_by=user, status="SHIPPED")

    # Asegurar que ambas tengan updated_at distinto
    now = timezone.now()
    PurchaseOrder.objects.filter(id=po_main.id).update(updated_at=now)
    PurchaseOrder.objects.filter(id=po_other.id).update(updated_at=now)

    base_url = "/api/purchase-orders/last-shipped/"

    # Filtro por provider principal
    res_main = auth_client.get(f"{base_url}?provider={provider.id}")
    assert res_main.status_code == status.HTTP_200_OK
    assert isinstance(res_main.data, dict)
    assert res_main.data.get("provider") == provider.id

    # Filtro por otro provider
    res_other = auth_client.get(f"{base_url}?provider={other_provider.id}")
    assert res_other.status_code == status.HTTP_200_OK
    assert isinstance(res_other.data, dict)
    assert res_other.data.get("provider") == other_provider.id


def test_last_shipped_no_results_returns_message(auth_client, provider, user):
    """Verifica que last-shipped sin resultados devuelva un mensaje."""
    # No hay órdenes SHIPPED del usuario
    url = "/api/purchase-orders/last-shipped/"
    res = auth_client.get(url)
    assert res.status_code == status.HTTP_200_OK
    assert isinstance(res.data, dict)
    assert res.data.get("detail") == "No existen órdenes enviadas."

    # Crear una orden SHIPPED de otro usuario para verificar que no se devuelve
    User = get_user_model()
    other_user = User.objects.create_user(username="other", password="pass")
    PurchaseOrder.objects.create(provider=provider, ordered_by=other_user, status="SHIPPED")

    res2 = auth_client.get(url)
    assert res2.status_code == status.HTTP_200_OK
    assert res2.data.get("detail") == "No existen órdenes enviadas."


def test_last_shipped_invalid_provider_param_returns_400(auth_client):
    """Verifica que last-shipped con provider inválido retorne 400."""
    url = "/api/purchase-orders/last-shipped/?provider=abc"
    res = auth_client.get(url)
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert "detail" in res.data


def test_received_products_success_with_ids(auth_client, provider, user, product1, product2):
    """Verifica la acción received-products con IDs de productos."""
    # Crear orden SHIPPED con ítems para el usuario y proveedor principal
    po = PurchaseOrder.objects.create(provider=provider, ordered_by=user, status="SHIPPED")
    PurchaseOrderItem.objects.create(order=po, product=product1, quantity_units=2)
    PurchaseOrderItem.objects.create(order=po, product=product2, quantity_units=3)

    url = f"/api/purchase-orders/received-products/?provider={provider.id}"
    # Marcar solo product1 como recibido
    payload = {"products": [product1.id]}
    res = auth_client.post(url, data=payload, format="json")
    assert res.status_code == status.HTTP_200_OK
    assert isinstance(res.data, list)
    # Debe devolver ambos productos de la orden
    assert len(res.data) == 2
    by_id = {row["id"]: row for row in res.data}
    assert by_id[product1.id]["received"]  # recibido
    assert not by_id[product1.id]["missing"]  # no falta
    assert not by_id[product2.id]["received"]  # no recibido
    assert by_id[product2.id]["missing"]   # falta


def test_received_products_success_with_barcodes(auth_client, provider, user, product1, product2):
    """Verifica la acción received-products con códigos de barras."""
    # Crear barcodes para los productos
    bc1 = ProductBarcode.objects.create(product=product1, code="BC-111", type=ProductBarcode.BarcodeType.EAN13)
    bc2 = ProductBarcode.objects.create(product=product2, code="BC-222", type=ProductBarcode.BarcodeType.EAN13)

    # Crear orden SHIPPED con ítems para el usuario
    po = PurchaseOrder.objects.create(provider=provider, ordered_by=user, status="SHIPPED")
    PurchaseOrderItem.objects.create(order=po, product=product1, quantity_units=5)
    PurchaseOrderItem.objects.create(order=po, product=product2, quantity_units=7)

    url = f"/api/purchase-orders/received-products/?provider={provider.id}"
    # Enviar barcodes en lugar de IDs, marcar ambos como recibidos
    payload = {"products": [bc1.code, bc2.code]}
    res = auth_client.post(url, data=payload, format="json")
    assert res.status_code == status.HTTP_200_OK
    assert isinstance(res.data, list)
    assert len(res.data) == 2
    for row in res.data:
        assert row["received"]  # ambos recibidos
        assert not row["missing"]  # ninguno falta


def test_received_products_missing_provider_returns_400(auth_client):
    """Verifica que received-products sin proveedor retorne 400."""
    url = "/api/purchase-orders/received-products/"
    res = auth_client.post(url, data={"products": []}, format="json")
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert "detail" in res.data


def test_received_products_invalid_provider_returns_400(auth_client):
    """Verifica que received-products con provider inválido retorne 400."""
    url = "/api/purchase-orders/received-products/?provider=abc"
    res = auth_client.post(url, data={"products": []}, format="json")
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert "detail" in res.data


def test_received_products_no_shipped_returns_message(auth_client, provider, product1):
    """Verifica que received-products sin órdenes SHIPPED devuelva mensaje."""
    # No existe orden SHIPPED para el proveedor
    url = f"/api/purchase-orders/received-products/?provider={provider.id}"
    res = auth_client.post(url, data={"products": [product1.id]}, format="json")
    assert res.status_code == status.HTTP_200_OK
    assert isinstance(res.data, dict)
    assert res.data.get("detail") == "No existen órdenes enviadas para este proveedor."


def test_received_products_products_not_list_returns_400(auth_client, provider, user):
    """Verifica que received-products con products no lista retorne 400."""
    # Crear una orden SHIPPED para pasar la validación de existencia
    PurchaseOrder.objects.create(provider=provider, ordered_by=user, status="SHIPPED")
    url = f"/api/purchase-orders/received-products/?provider={provider.id}"
    # Enviar un dict en lugar de lista
    res = auth_client.post(url, data={"products": {"a": 1}}, format="json")
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert "detail" in res.data
