from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from django.db.models import Prefetch, Exists, OuterRef, Subquery, Value, BooleanField, IntegerField
from django.utils import timezone
import datetime

from django.conf import settings
from ftplib import FTP
import io
import json
from .models import Product, Provider, ProductFavorite
from purchase_orders.models import PurchaseOrder
from .serializers import (
    ProductSerializer,
    ProviderSerializer,
)
from market.models import LoginHistory
from received.models import Reception

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

            # Filtro por proveedor: acepta 'provider' o 'provider_id'
            provider_q = request.query_params.get("provider") or request.query_params.get("provider_id")
            if provider_q:
                try:
                    pid = int(str(provider_q).strip())
                    if pid > 0:
                        qs = qs.filter(providers__id=pid)
                except Exception:
                    # Si no es entero, filtrar por nombre del proveedor (icontains)
                    qs = qs.filter(providers__name__icontains=str(provider_q).strip())

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

    def list(self, request, *args, **kwargs):
        """
        Lista productos con paginación automática.
        
        Parámetros de consulta disponibles:
        - page: Número de página (ej: ?page=2)
        - page_size: Tamaño de página personalizado (ej: ?page_size=50)
        - barcode: Filtrar por código de barras exacto
        - name o q: Búsqueda por nombre (contiene)
        - provider o provider_id: Filtrar por proveedor (ID o nombre)
        - ordering: Ordenar por nombre (name o -name)
        """
        queryset = self.filter_queryset(self.get_queryset())
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

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

    def list(self, request, *args, **kwargs):
        # Resolve user's market from latest LoginHistory
        last = (
            LoginHistory.objects.select_related("market")
            .filter(user=request.user)
            .order_by("-timestamp")
            .first()
        )
        if not last:
            return Response(
                {"detail": "No market found for current user (no login history)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        market = last.market
        # Annotate providers with has_draft_reception flag
        subq = Reception.objects.filter(
            status=Reception.Status.DRAFT,
            market=market,
            purchase_order__provider=OuterRef("pk"),
        )
        latest_draft_po_id = Subquery(
            subq.order_by("-created_at").values("purchase_order_id")[:1]
        )
        # Annotate providers with last SHIPPED purchase order id for this market
        shipped_po_subq = PurchaseOrder.objects.filter(
            status=PurchaseOrder.Status.SHIPPED,
            market=market,
            provider=OuterRef("pk"),
        )
        last_shipped_order_id = Subquery(
            shipped_po_subq.order_by("-created_at").values("id")[:1]
        )

        qs = Provider.objects.all().annotate(
            has_draft_reception=Exists(subq),
            draft_reception_order_id=latest_draft_po_id,
            last_shipped_order_id=last_shipped_order_id,
        )

        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)
