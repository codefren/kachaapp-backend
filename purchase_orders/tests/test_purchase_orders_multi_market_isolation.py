"""Tests de aislamiento multi-market para Purchase Orders.

Verifica que:
- Cada usuario solo puede ver las órdenes de su market/organización
- No hay filtración de datos entre organizaciones diferentes
- Los endpoints de consulta respetan el aislamiento
- Superusers pueden ver todas las órdenes
"""

import pytest
from rest_framework import status

from purchase_orders.models import PurchaseOrder


@pytest.mark.django_db
class TestPurchaseOrderMultiMarketIsolation:
    """Suite de tests para validar aislamiento de datos entre markets."""

    def test_user_only_sees_purchase_orders_from_their_market(
        self,
        auth_client_a,
        auth_client_b,
        user_a,
        user_b,
        market_a,
        market_b,
        provider_a,
        provider_b,
        product_a,
        product_b,
        login_history_a,
        login_history_b,
    ):
        """Usuario solo debe ver órdenes de compra de su propio market."""
        # Arrange: Crear órdenes en market A
        url = "/api/purchase-orders/"
        payload_a = {
            "provider": provider_a.id,
            "status": "PLACED",
            "notes": "Orden de Market A",
            "items": [
                {"product": product_a.id, "quantity_units": 5, "purchase_unit": "boxes"},
            ],
        }
        res_a = auth_client_a.post(url, data=payload_a, format="json")
        assert res_a.status_code == status.HTTP_201_CREATED
        order_a_id = res_a.data["id"]

        # Crear órdenes en market B
        payload_b = {
            "provider": provider_b.id,
            "status": "PLACED",
            "notes": "Orden de Market B",
            "items": [
                {"product": product_b.id, "quantity_units": 3, "purchase_unit": "boxes"},
            ],
        }
        res_b = auth_client_b.post(url, data=payload_b, format="json")
        assert res_b.status_code == status.HTTP_201_CREATED
        order_b_id = res_b.data["id"]

        # Act & Assert: Usuario A solo ve sus órdenes
        list_a = auth_client_a.get(url)
        assert list_a.status_code == status.HTTP_200_OK
        order_ids_a = [order["id"] for order in list_a.data]
        assert order_a_id in order_ids_a
        assert order_b_id not in order_ids_a, "User A no debe ver órdenes de Market B"

        # Usuario B solo ve sus órdenes
        list_b = auth_client_b.get(url)
        assert list_b.status_code == status.HTTP_200_OK
        order_ids_b = [order["id"] for order in list_b.data]
        assert order_b_id in order_ids_b
        assert order_a_id not in order_ids_b, "User B no debe ver órdenes de Market A"

    def test_user_cannot_access_purchase_order_from_different_market(
        self,
        auth_client_a,
        auth_client_b,
        market_a,
        market_b,
        provider_a,
        product_a,
        login_history_a,
        login_history_b,
    ):
        """Usuario no puede acceder a detalle de orden de otro market."""
        # Arrange: Crear orden en market A
        url = "/api/purchase-orders/"
        payload = {
            "provider": provider_a.id,
            "status": "DRAFT",
            "items": [
                {"product": product_a.id, "quantity_units": 2, "purchase_unit": "boxes"},
            ],
        }
        res_create = auth_client_a.post(url, data=payload, format="json")
        assert res_create.status_code == status.HTTP_201_CREATED
        order_id = res_create.data["id"]

        # Act: Usuario B intenta acceder a orden de Market A
        detail_url = f"/api/purchase-orders/{order_id}/"
        res_b = auth_client_b.get(detail_url)

        # Assert: Debe retornar 404 (no encontrado, por filtrado de organización)
        assert res_b.status_code == status.HTTP_404_NOT_FOUND

    def test_create_purchase_order_assigns_correct_market_per_user(
        self,
        auth_client_a,
        auth_client_b,
        user_a,
        user_b,
        market_a,
        market_b,
        provider_a,
        provider_b,
        product_a,
        product_b,
        login_history_a,
        login_history_b,
    ):
        """Cada usuario crea órdenes que se asignan automáticamente a su market."""
        url = "/api/purchase-orders/"

        # Arrange & Act: Usuario A crea orden
        payload_a = {
            "provider": provider_a.id,
            "status": "PLACED",
            "items": [
                {"product": product_a.id, "quantity_units": 10, "purchase_unit": "boxes"},
            ],
        }
        res_a = auth_client_a.post(url, data=payload_a, format="json")

        # Assert: Se asigna market A
        assert res_a.status_code == status.HTTP_201_CREATED
        assert res_a.data["market"] == market_a.id
        assert res_a.data["ordered_by"] == user_a.id

        # Arrange & Act: Usuario B crea orden
        payload_b = {
            "provider": provider_b.id,
            "status": "PLACED",
            "items": [
                {"product": product_b.id, "quantity_units": 7, "purchase_unit": "boxes"},
            ],
        }
        res_b = auth_client_b.post(url, data=payload_b, format="json")

        # Assert: Se asigna market B
        assert res_b.status_code == status.HTTP_201_CREATED
        assert res_b.data["market"] == market_b.id
        assert res_b.data["ordered_by"] == user_b.id

        # Verificar en base de datos
        order_a = PurchaseOrder.objects.get(id=res_a.data["id"])
        assert order_a.market_id == market_a.id
        assert order_a.ordered_by_id == user_a.id

        order_b = PurchaseOrder.objects.get(id=res_b.data["id"])
        assert order_b.market_id == market_b.id
        assert order_b.ordered_by_id == user_b.id

    def test_list_purchase_orders_filters_by_user_market(
        self,
        auth_client_a,
        auth_client_b,
        market_a,
        market_b,
        provider_a,
        provider_b,
        product_a,
        product_b,
        login_history_a,
        login_history_b,
    ):
        """Listar órdenes debe filtrar automáticamente por market del usuario."""
        # Arrange: Crear múltiples órdenes en ambos markets
        url = "/api/purchase-orders/"

        # 3 órdenes en Market A
        for i in range(3):
            payload = {
                "provider": provider_a.id,
                "status": "PLACED",
                "notes": f"Orden A-{i}",
                "items": [
                    {"product": product_a.id, "quantity_units": i + 1, "purchase_unit": "boxes"},
                ],
            }
            res = auth_client_a.post(url, data=payload, format="json")
            assert res.status_code == status.HTTP_201_CREATED

        # 2 órdenes en Market B
        for i in range(2):
            payload = {
                "provider": provider_b.id,
                "status": "DRAFT",
                "notes": f"Orden B-{i}",
                "items": [
                    {"product": product_b.id, "quantity_units": i + 1, "purchase_unit": "boxes"},
                ],
            }
            res = auth_client_b.post(url, data=payload, format="json")
            assert res.status_code == status.HTTP_201_CREATED

        # Act & Assert: Usuario A solo ve 3 órdenes
        list_a = auth_client_a.get(url)
        assert list_a.status_code == status.HTTP_200_OK
        assert len(list_a.data) == 3
        # Todas deben ser de Market A
        for order in list_a.data:
            assert order["market"] == market_a.id

        # Usuario B solo ve 2 órdenes
        list_b = auth_client_b.get(url)
        assert list_b.status_code == status.HTTP_200_OK
        assert len(list_b.data) == 2
        # Todas deben ser de Market B
        for order in list_b.data:
            assert order["market"] == market_b.id

    def test_superuser_sees_all_purchase_orders(
        self,
        auth_client_a,
        auth_client_b,
        auth_client_superuser,
        superuser,
        market_a,
        market_b,
        provider_a,
        provider_b,
        product_a,
        product_b,
        login_history_a,
        login_history_b,
    ):
        """Superuser debe ver órdenes de todos los markets sin filtrado."""
        # Arrange: Crear órdenes en ambos markets
        url = "/api/purchase-orders/"

        payload_a = {
            "provider": provider_a.id,
            "status": "PLACED",
            "items": [
                {"product": product_a.id, "quantity_units": 4, "purchase_unit": "boxes"},
            ],
        }
        res_a = auth_client_a.post(url, data=payload_a, format="json")
        assert res_a.status_code == status.HTTP_201_CREATED
        order_a_id = res_a.data["id"]

        payload_b = {
            "provider": provider_b.id,
            "status": "PLACED",
            "items": [
                {"product": product_b.id, "quantity_units": 6, "purchase_unit": "boxes"},
            ],
        }
        res_b = auth_client_b.post(url, data=payload_b, format="json")
        assert res_b.status_code == status.HTTP_201_CREATED
        order_b_id = res_b.data["id"]

        # Act: Superuser lista todas las órdenes
        list_super = auth_client_superuser.get(url)

        # Assert: Debe ver ambas órdenes
        assert list_super.status_code == status.HTTP_200_OK
        order_ids = [order["id"] for order in list_super.data]
        assert order_a_id in order_ids, "Superuser debe ver órdenes de Market A"
        assert order_b_id in order_ids, "Superuser debe ver órdenes de Market B"

    def test_purchase_order_actions_respect_market_isolation(
        self,
        auth_client_a,
        auth_client_b,
        market_a,
        market_b,
        provider_a,
        provider_b,
        product_a,
        product_b,
        login_history_a,
        login_history_b,
    ):
        """Actions como 'has-ordered-today' deben respetar filtrado por market."""
        # Arrange: Crear órdenes en ambos markets
        url = "/api/purchase-orders/"

        # Usuario A crea orden
        payload_a = {
            "provider": provider_a.id,
            "status": "PLACED",
            "items": [
                {"product": product_a.id, "quantity_units": 2, "purchase_unit": "boxes"},
            ],
        }
        res_a = auth_client_a.post(url, data=payload_a, format="json")
        assert res_a.status_code == status.HTTP_201_CREATED

        # Usuario B crea orden
        payload_b = {
            "provider": provider_b.id,
            "status": "PLACED",
            "items": [
                {"product": product_b.id, "quantity_units": 3, "purchase_unit": "boxes"},
            ],
        }
        res_b = auth_client_b.post(url, data=payload_b, format="json")
        assert res_b.status_code == status.HTTP_201_CREATED

        # Act & Assert: has-ordered-today con provider específico
        has_ordered_url = "/api/purchase-orders/has-ordered-today/"

        # Usuario A debe ver que ordenó del proveedor A
        res_check_a = auth_client_a.get(f"{has_ordered_url}?provider={provider_a.id}")
        assert res_check_a.status_code == status.HTTP_200_OK
        assert res_check_a.data["has_ordered_today"] is True

        # Usuario A NO debe ver órdenes del proveedor B (de otra organización)
        res_check_a_b = auth_client_a.get(f"{has_ordered_url}?provider={provider_b.id}")
        assert res_check_a_b.status_code == status.HTTP_200_OK
        assert res_check_a_b.data["has_ordered_today"] is False

        # Usuario B debe ver que ordenó del proveedor B
        res_check_b = auth_client_b.get(f"{has_ordered_url}?provider={provider_b.id}")
        assert res_check_b.status_code == status.HTTP_200_OK
        assert res_check_b.data["has_ordered_today"] is True

        # Usuario B NO debe ver órdenes del proveedor A (de otra organización)
        res_check_b_a = auth_client_b.get(f"{has_ordered_url}?provider={provider_a.id}")
        assert res_check_b_a.status_code == status.HTTP_200_OK
        assert res_check_b_a.data["has_ordered_today"] is False


@pytest.mark.django_db
class TestPurchaseOrderCrossMarketSecurity:
    """Tests adicionales de seguridad para operaciones cross-market."""

    def test_user_cannot_update_purchase_order_from_different_market(
        self,
        auth_client_a,
        auth_client_b,
        market_a,
        market_b,
        provider_a,
        product_a,
        login_history_a,
        login_history_b,
    ):
        """Usuario no puede actualizar orden de otro market."""
        # Arrange: Crear orden en market A
        url = "/api/purchase-orders/"
        payload = {
            "provider": provider_a.id,
            "status": "DRAFT",
            "items": [
                {"product": product_a.id, "quantity_units": 5, "purchase_unit": "boxes"},
            ],
        }
        res_create = auth_client_a.post(url, data=payload, format="json")
        assert res_create.status_code == status.HTTP_201_CREATED
        order_id = res_create.data["id"]

        # Act: Usuario B intenta actualizar orden de Market A
        update_url = f"/api/purchase-orders/{order_id}/"
        update_payload = {
            "status": "PLACED",
            "notes": "Intento de actualización cross-market",
            "items": [
                {"product": product_a.id, "quantity_units": 10, "purchase_unit": "boxes"},
            ],
        }
        res_update = auth_client_b.patch(update_url, data=update_payload, format="json")

        # Assert: Debe retornar 404 (orden no encontrada para ese usuario)
        assert res_update.status_code == status.HTTP_404_NOT_FOUND

        # Verificar que la orden no fue modificada
        order = PurchaseOrder.objects.get(id=order_id)
        assert order.status == "DRAFT"
        assert order.notes != "Intento de actualización cross-market"

    def test_empty_queryset_when_user_has_no_organization(
        self,
        api_client,
        db,
    ):
        """Usuario sin organización debe recibir queryset vacío."""
        # Arrange: Crear usuario sin organización
        from django.contrib.auth import get_user_model
        User = get_user_model()
        user_no_org = User.objects.create_user(
            username="user_no_org",
            password="pass1234",
            organization=None  # Sin organización
        )
        api_client.force_authenticate(user=user_no_org)

        # Act: Intentar listar órdenes
        url = "/api/purchase-orders/"
        res = api_client.get(url)

        # Assert: Debe retornar lista vacía
        assert res.status_code == status.HTTP_200_OK
        assert len(res.data) == 0
