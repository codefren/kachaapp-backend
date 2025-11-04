"""Views for purchase orders."""

import datetime
from django.db.models import Prefetch
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from kachadigitalbcn.users.mixins import (
    OrganizationQuerySetMixin,
    OrganizationPermissionMixin
)

from proveedores.models import ProductBarcode
from .models import PurchaseOrder, PurchaseOrderItem
from .serializers import PurchaseOrderSerializer, PurchaseOrderItemSerializer


class PurchaseOrderViewSet(OrganizationQuerySetMixin, OrganizationPermissionMixin, viewsets.ModelViewSet):
    """ViewSet para órdenes de compra con filtrado automático por organización."""
    
    queryset = PurchaseOrder.objects.select_related("provider", "ordered_by", "market").prefetch_related(
        Prefetch("items", queryset=PurchaseOrderItem.objects.select_related("product").order_by("-created_at"))
    )
    serializer_class = PurchaseOrderSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "post", "put", "patch", "head", "options"]
    organization_field_path = 'market__organization'  # PurchaseOrder -> Market -> Organization

    @action(detail=False, methods=["get"], url_path="has-ordered-today")
    def has_ordered_today(self, request):
        """Retorna si el usuario actual ha creado al menos una orden hoy.

        Respuesta: {"has_ordered_today": true|false}
        """
        today = timezone.now().date()
        qs = PurchaseOrder.objects.filter(
            ordered_by=request.user,
            created_at__date=today,
        )
        provider_id = request.query_params.get("provider")
        if provider_id is not None:
            # Validación básica de entero
            try:
                provider_id_int = int(provider_id)
            except (TypeError, ValueError):
                return Response(
                    {"detail": "El parámetro 'provider' debe ser un entero."}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            qs = qs.filter(provider_id=provider_id_int)
        has_order = qs.exists()
        return Response({"has_ordered_today": has_order})

    @action(detail=False, methods=["get"], url_path="by-day")
    def by_day(self, request):
        """Lista órdenes por día exacto usando ?date=YYYY-MM-DD.

        Si no existen órdenes para el día, devuelve un mensaje en lugar de una lista vacía.
        """
        date_str = request.query_params.get("date")
        if not date_str:
            return Response(
                {"detail": "El parámetro 'date' es requerido."},
                status=status.HTTP_400_BAD_REQUEST
            )
        try:
            d = datetime.date.fromisoformat(date_str)
        except ValueError:
            return Response(
                {"detail": "El parámetro 'date' no tiene el formato correcto (YYYY-MM-DD)."}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        base_qs = self.get_queryset().filter(created_at__date=d, status=PurchaseOrder.Status.DRAFT)
        # Filtro opcional por proveedor: ?provider=<id>
        provider_id = request.query_params.get("provider")
        if provider_id is not None:
            try:
                provider_id_int = int(provider_id)
            except (TypeError, ValueError):
                return Response(
                    {"detail": "El parámetro 'provider' debe ser un entero."}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            base_qs = base_qs.filter(provider_id=provider_id_int)

        queryset = self.filter_queryset(base_qs.order_by("-created_at"))

        # Si no hay ninguna orden para ese día
        if not queryset.exists():
            return Response(
                {"detail": "No existen órdenes para el día seleccionado."}, 
                status=status.HTTP_200_OK
            )

        # Tomar la más reciente y devolver un único objeto
        obj = queryset.first()
        serializer = self.get_serializer(obj)
        return Response(serializer.data)

    @action(detail=False, methods=["post"], url_path="received-products")
    def received_products(self, request):
        """Recibe una lista de productos recibidos y devuelve los productos
        de la última orden SHIPPED del usuario autenticado para un proveedor,
        marcando cuáles se recibieron y cuáles faltan.

        Entrada:
        - Query param: provider=<id>
        - Body JSON: {"products": [<product_id o barcode>, ...]}

        Respuesta: lista de objetos con
        { id, name, quantity_units, received: bool, missing: bool }
        """
        provider_id = request.query_params.get("provider")
        if provider_id is None:
            return Response(
                {"detail": "El parámetro 'provider' es requerido."}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        try:
            provider_id_int = int(provider_id)
        except (TypeError, ValueError):
            return Response(
                {"detail": "El parámetro 'provider' debe ser un entero."}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        # Obtener última orden SHIPPED del usuario y proveedor
        po_qs = (
            self.get_queryset()
            .filter(
                status=PurchaseOrder.Status.SHIPPED, 
                ordered_by=request.user, 
                provider_id=provider_id_int
            )
            .order_by("-updated_at", "-created_at")
        )
        if not po_qs.exists():
            return Response(
                {"detail": "No existen órdenes enviadas para este proveedor."}, 
                status=status.HTTP_200_OK
            )
        po = po_qs.first()

        # Construir set de productos recibidos a partir del payload (IDs o barcodes)
        payload_list = request.data.get("products", []) or []
        received_ids: set[int] = set()
        if not isinstance(payload_list, (list, tuple)):
            return Response(
                {"detail": "El cuerpo debe incluir 'products' como lista."}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        # Resolver entradas: si es entero -> product_id; si es string -> intentar como barcode
        for entry in payload_list:
            # Intentar convertir a int para tratar como product_id
            pid = None
            if isinstance(entry, int):
                pid = entry
            else:
                # Podría venir como string de número o un barcode alfanumérico
                if isinstance(entry, str):
                    try:
                        pid = int(entry)
                    except (TypeError, ValueError):
                        # Buscar por barcode exacto
                        bc = ProductBarcode.objects.filter(code=entry).only("product_id").first()
                        if bc:
                            pid = bc.product_id
            if pid is not None:
                received_ids.add(int(pid))

        # Recorrer los productos de la orden
        items = (
            PurchaseOrderItem.objects.select_related("product")
            .filter(order=po)
            .order_by("product__name")
        )
        result = []
        for it in items:
            pid = it.product_id
            is_received = pid in received_ids
            result.append(
                {
                    "id": pid,
                    "name": it.product.name,
                    "quantity_units": it.quantity_units,
                    "received": is_received,
                    "missing": not is_received,
                }
            )

        return Response(result, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path="last-shipped")
    def last_shipped(self, request):
        """Devuelve la última orden en estado SHIPPED.

        Si no existe ninguna, devuelve un mensaje informativo con HTTP 200.
        """
        qs = self.get_queryset().filter(
            status=PurchaseOrder.Status.SHIPPED, 
            ordered_by=request.user
        )
        # Filtro opcional por proveedor: ?provider=<id>
        provider_id = request.query_params.get("provider")
        if provider_id is not None:
            try:
                provider_id_int = int(provider_id)
            except (TypeError, ValueError):
                return Response(
                    {"detail": "El parámetro 'provider' debe ser un entero."}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            qs = qs.filter(provider_id=provider_id_int)

        qs = qs.order_by("-updated_at", "-created_at")
        if not qs.exists():
            return Response(
                {"detail": "No existen órdenes enviadas."}, 
                status=status.HTTP_200_OK
            )
        obj = qs.first()
        serializer = self.get_serializer(obj)
        return Response(serializer.data)


class PurchaseOrderItemViewSet(OrganizationQuerySetMixin, OrganizationPermissionMixin, viewsets.ModelViewSet):
    """ViewSet para items de órdenes de compra con filtrado automático por organización."""
    
    queryset = PurchaseOrderItem.objects.select_related("order", "product").all()
    serializer_class = PurchaseOrderItemSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "post", "put", "patch", "head", "options"]
    organization_field_path = 'order__market__organization'  # PurchaseOrderItem -> PurchaseOrder -> Market -> Organization
