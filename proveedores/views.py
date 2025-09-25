from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from django.db.models import Prefetch
from django.utils import timezone
import datetime

from django.conf import settings
from ftplib import FTP
import io
import json
from .models import Product, Provider, PurchaseOrder, PurchaseOrderItem, ProductFavorite
from .serializers import (
    PurchaseOrderSerializer,
    PurchaseOrderItemSerializer,
    ProductSerializer,
    ProviderSerializer,
)

FTP_HOST = getattr(settings, "PROVEEDORES_FTP_HOST", "localhost")
FTP_USER = getattr(settings, "PROVEEDORES_FTP_USER", "anonymous")
FTP_PASS = getattr(settings, "PROVEEDORES_FTP_PASS", "")
FTP_JSON_PATH = getattr(settings, "PROVEEDORES_FTP_PATH", "/products.json")


@api_view(["POST"])  # type: ignore[valid-type]
def load_products_from_ftp(request):
    """Descarga el archivo JSON del FTP y carga/actualiza productos y proveedores.

    Formato esperado del JSON:
    [
      {
        "sku": "123",
        "name": "Manzana",
        "providers": [
            {"name": "Proveedor A"},
            {"name": "Proveedor B"}
        ]
      },
      ...
    ]
    """
    # Conectar y descargar archivo
    with FTP(FTP_HOST) as ftp:
        ftp.login(FTP_USER, FTP_PASS)
        bytes_io = io.BytesIO()
        ftp.retrbinary(f"RETR {FTP_JSON_PATH}", bytes_io.write)
        bytes_io.seek(0)
        data = json.load(io.TextIOWrapper(bytes_io, encoding="utf-8"))

    created, updated = 0, 0
    for item in data:
        sku = item.get("sku")
        name = item.get("name")
        provider_objs = []
        for prov in item.get("providers", []):
            provider_obj, _ = Provider.objects.get_or_create(name=prov.get("name"))
            provider_objs.append(provider_obj)
        product_obj, created_flag = Product.objects.update_or_create(
            sku=sku,
            defaults={"name": name},
        )
        product_obj.providers.set(provider_objs)
        product_obj.save()
        if created_flag:
            created += 1
        else:
            updated += 1

    return Response({"created": created, "updated": updated})


@api_view(["GET"])  # type: ignore[valid-type]
@permission_classes([permissions.AllowAny])
def proveedores_root(request):
    """Simple root endpoint for proveedores module."""
    return Response({"message": "Proveedores API root"})


class PurchaseOrderViewSet(viewsets.ModelViewSet):
    queryset = PurchaseOrder.objects.select_related("provider", "ordered_by").prefetch_related(
        Prefetch("items", queryset=PurchaseOrderItem.objects.select_related("product"))
    )
    serializer_class = PurchaseOrderSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "post", "put", "patch", "head", "options"]

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
                return Response({"detail": "El parámetro 'provider' debe ser un entero."}, status=status.HTTP_400_BAD_REQUEST)
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
            return Response({"detail": "El parámetro 'date' es requerido."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            d = datetime.date.fromisoformat(date_str)
        except ValueError:
            return Response({"detail": "El parámetro 'date' no tiene el formato correcto (YYYY-MM-DD)."}, status=status.HTTP_400_BAD_REQUEST)

        base_qs = self.get_queryset().filter(created_at__date=d)
        # Filtro opcional por proveedor: ?provider=<id>
        provider_id = request.query_params.get("provider")
        if provider_id is not None:
            try:
                provider_id_int = int(provider_id)
            except (TypeError, ValueError):
                return Response({"detail": "El parámetro 'provider' debe ser un entero."}, status=status.HTTP_400_BAD_REQUEST)
            base_qs = base_qs.filter(provider_id=provider_id_int)

        queryset = self.filter_queryset(base_qs.order_by("-created_at"))

        # Si no hay ninguna orden para ese día
        if not queryset.exists():
            return Response({"detail": "No existen órdenes para el día seleccionado."}, status=status.HTTP_200_OK)

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
            return Response({"detail": "El parámetro 'provider' es requerido."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            provider_id_int = int(provider_id)
        except (TypeError, ValueError):
            return Response({"detail": "El parámetro 'provider' debe ser un entero."}, status=status.HTTP_400_BAD_REQUEST)

        # Obtener última orden SHIPPED del usuario y proveedor
        po_qs = (
            self.get_queryset()
            .filter(status=PurchaseOrder.Status.SHIPPED, ordered_by=request.user, provider_id=provider_id_int)
            .order_by("-updated_at", "-created_at")
        )
        if not po_qs.exists():
            return Response({"detail": "No existen órdenes enviadas para este proveedor."}, status=status.HTTP_200_OK)
        po = po_qs.first()

        # Construir set de productos recibidos a partir del payload (IDs o barcodes)
        payload_list = request.data.get("products", []) or []
        received_ids: set[int] = set()
        if not isinstance(payload_list, (list, tuple)):
            return Response({"detail": "El cuerpo debe incluir 'products' como lista."}, status=status.HTTP_400_BAD_REQUEST)

        # Resolver entradas: si es entero -> product_id; si es string -> intentar como barcode
        from .models import ProductBarcode

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
        qs = self.get_queryset().filter(status=PurchaseOrder.Status.SHIPPED, ordered_by=request.user)
        # Filtro opcional por proveedor: ?provider=<id>
        provider_id = request.query_params.get("provider")
        if provider_id is not None:
            try:
                provider_id_int = int(provider_id)
            except (TypeError, ValueError):
                return Response({"detail": "El parámetro 'provider' debe ser un entero."}, status=status.HTTP_400_BAD_REQUEST)
            qs = qs.filter(provider_id=provider_id_int)

        qs = qs.order_by("-updated_at", "-created_at")
        if not qs.exists():
            return Response({"detail": "No existen órdenes enviadas."}, status=status.HTTP_200_OK)
        obj = qs.first()
        serializer = self.get_serializer(obj)
        return Response(serializer.data)


class PurchaseOrderItemViewSet(viewsets.ModelViewSet):
    queryset = PurchaseOrderItem.objects.select_related("order", "product").all()
    serializer_class = PurchaseOrderItemSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "post", "put", "patch", "head", "options"]


class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ProductSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = (
            Product.objects.all()
            .prefetch_related(
                "providers",
                "barcodes",
                "favorites",
            )
        )
        # Filtrar por código de barras exacto si se provee
        request = getattr(self, 'request', None)
        if request is not None:
            code = request.query_params.get("barcode")
            if code:
                qs = qs.filter(barcodes__code=code)
            # Búsqueda por nombre (icontains). También acepta alias 'q'.
            name_q = request.query_params.get("name") or request.query_params.get("q")
            if name_q:
                qs = qs.filter(name__icontains=name_q)

            # Ordenamiento por nombre: ?ordering=name (ascendente) o ?ordering=-name (descendente)
            ordering = request.query_params.get("ordering")
            if ordering == "name":
                qs = qs.order_by("name")
            elif ordering == "-name":
                qs = qs.order_by("-name")
            else:
                # Orden por defecto: nombre ascendente
                qs = qs.order_by("name")
        else:
            qs = qs.order_by("name")

        return qs.distinct()

    @action(detail=True, methods=["post"], url_path="favorite")
    def favorite(self, request, pk=None):
        product = self.get_object()
        ProductFavorite.objects.get_or_create(user=request.user, product=product)
        return Response({"detail": "Product added to favorites."}, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="unfavorite")
    def unfavorite(self, request, pk=None):
        product = self.get_object()
        ProductFavorite.objects.filter(user=request.user, product=product).delete()
        return Response({"detail": "Product removed from favorites."}, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path="my-favorites")
    def my_favorites(self, request):
        qs = self.get_queryset().filter(favorites__user=request.user)
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)


class ProviderViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Provider.objects.all()
    serializer_class = ProviderSerializer
    permission_classes = [permissions.IsAuthenticated]
