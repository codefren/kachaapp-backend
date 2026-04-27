"""Views for purchase orders."""
import datetime
from collections import defaultdict

from django.core.mail import EmailMessage
from django.db import transaction
from django.db.models import Prefetch
from django.http import HttpResponse
from django.utils import timezone

from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from kachadigitalbcn.common.permissions import IsMasterUser
from kachadigitalbcn.users.mixins import (
    OrganizationPermissionMixin,
    OrganizationQuerySetMixin,
)
from market.models import Market
from proveedores.models import Product, ProductBarcode

from .export_utils import (
    build_grouped_purchase_order_excel,
    build_grouped_purchase_order_pdf,
    build_purchase_order_excel,
    build_purchase_order_pdf,
)
from .models import PurchaseOrder, PurchaseOrderItem
from .serializers import PurchaseOrderItemSerializer, PurchaseOrderSerializer


class PurchaseOrderViewSet(
    OrganizationQuerySetMixin,
    OrganizationPermissionMixin,
    viewsets.ModelViewSet,
):
    """ViewSet para órdenes de compra con filtrado automático por organización."""

    queryset = PurchaseOrder.objects.select_related(
        "provider",
        "ordered_by",
        "market",
        "sent_by",
        "locked_by",
    ).prefetch_related(
        Prefetch(
            "items",
            queryset=PurchaseOrderItem.objects.select_related("product").order_by("-created_at"),
        )
    )
    serializer_class = PurchaseOrderSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "post", "put", "patch", "delete", "head", "options"]
    organization_field_path = "market__organization"

    def perform_destroy(self, instance):
        from market.models import Shift
        from rest_framework.exceptions import PermissionDenied
        if instance.market and not self.request.user.is_superuser and str(self.request.user.role).upper() != "MASTER":
            active_shift = Shift.objects.filter(
                user=self.request.user,
                ended_at__isnull=True,
            ).select_related("market").first()
            if not active_shift or not active_shift.market:
                raise PermissionDenied("No tienes una jornada activa para borrar pedidos.")
            if active_shift.market.id != instance.market.id:
                raise PermissionDenied(f"No puedes borrar pedidos de {instance.market.name}.")
        instance.delete()

    def perform_update(self, serializer):
        from market.models import Shift
        from rest_framework.exceptions import PermissionDenied
        order = serializer.instance
        if order.market:
            active_shift = Shift.objects.filter(
                user=self.request.user,
                ended_at__isnull=True,
            ).select_related("market").first()
            # Superusuarios y MASTER pueden modificar cualquier pedido
            if not self.request.user.is_superuser and str(self.request.user.role).upper() != "MASTER":
                if not active_shift or not active_shift.market:
                    raise PermissionDenied("No tienes una jornada activa para modificar pedidos.")
                if active_shift.market.id != order.market.id:
                    raise PermissionDenied(f"No puedes modificar pedidos de {order.market.name}. Tu jornada activa es en {active_shift.market.name}.")
        serializer.save()

    def get_queryset(self):
        qs = super().get_queryset()
        provider_id = self.request.query_params.get("provider")
        if provider_id:
            try:
                qs = qs.filter(provider_id=int(provider_id))
            except (TypeError, ValueError):
                pass
        return qs

    def _build_order_email_body(self, order):
        provider_name = order.provider.name or "Proveedor"
        contact_name = order.provider.contact_person or provider_name

        return (
            "Hola {},\n\n"
            "Adjuntamos el pedido de compra #{} en formato Excel y PDF.\n\n"
            "Proveedor: {}\n"
            "Tienda: {}\n"
            "Estado: {}\n"
            "Fecha pedido: {}\n"
            "Notas: {}\n\n"
            "Saludos,\n"
            "Kacha Digital BCN"
        ).format(
            contact_name,
            order.id,
            provider_name,
            order.market.name if order.market else "Sin tienda",
            order.status,
            order.created_at.strftime("%d/%m/%Y %H:%M") if order.created_at else "",
            order.notes or "Sin notas",
        )

    def _mark_order_as_sent(self, order, recipient, user):
        order.sent_at = timezone.now()
        order.sent_to_email = recipient
        order.sent_by = user

        if order.status == PurchaseOrder.Status.PLACED:
            order.status = PurchaseOrder.Status.IN_PROCESS

        order.save(
            update_fields=[
                "sent_at",
                "sent_to_email",
                "sent_by",
                "status",
                "updated_at",
            ]
        )

    def _send_single_order_email(self, order, user):
        if not order.provider:
            raise ValueError("La orden no tiene proveedor asociado.")

        if not order.provider.email:
            raise ValueError("El proveedor no tiene email configurado.")

        recipient = order.provider.email.strip()

        excel_file = build_purchase_order_excel(order)
        pdf_file = build_purchase_order_pdf(order)

        provider_name = order.provider.name or "Proveedor"

        email = EmailMessage(
            subject="Pedido de compra #{} - {}".format(order.id, provider_name),
            body=self._build_order_email_body(order),
            to=[recipient],
        )

        email.attach(
            "pedido_{}.xlsx".format(order.id),
            excel_file.getvalue(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        email.attach(
            "pedido_{}.pdf".format(order.id),
            pdf_file.getvalue(),
            "application/pdf",
        )

        email.send(fail_silently=False)
        self._mark_order_as_sent(order, recipient, user)

        return recipient

    @action(
        detail=False,
        methods=["get"],
        url_path="pivot",
        permission_classes=[permissions.IsAuthenticated, IsMasterUser],
    )
    def pivot(self, request):
        """
        Vista pivot:
        filas = productos
        columnas = tiendas
        total = suma horizontal por producto
        """
        provider_id = request.query_params.get("provider")

        if not provider_id:
            return Response(
                {"detail": "El parámetro 'provider' es requerido."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            provider_id_int = int(provider_id)
        except (TypeError, ValueError):
            return Response(
                {"detail": "El parámetro 'provider' debe ser un entero."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        orders = (
            self.get_queryset()
            .filter(provider_id=provider_id_int)
            .select_related("market", "provider")
            .prefetch_related("items__product")
            .order_by("market__name", "created_at")
        )

        markets = {}
        products = {}

        for order in orders:
            market_id = order.market.id if order.market else None
            market_name = order.market.name if order.market else "Sin tienda"

            markets[market_id] = {
                "id": market_id,
                "name": market_name,
                "order_id": order.id,
                "status": order.status,
                "sent": bool(order.sent_at),
                "sent_at": order.sent_at,
                "is_locked": order.is_locked,
                "locked_by": order.locked_by_id,
                "locked_by_username": order.locked_by.username if order.locked_by else "",
                "lock_expires_at": order.lock_expires_at,
            }

            for item in order.items.all():
                p = item.product
                if not p:
                    continue

                if p.id not in products:
                    products[p.id] = {
                        "product_id": p.id,
                        "name": p.name,
                        "sku": getattr(p, "sku", "") or "",
                        "barcode": "",
                        "purchase_unit": item.purchase_unit or "boxes",
                        "amount_boxes": getattr(p, "amount_boxes", 0) or 0,
                        "total": 0,
                        "markets": {},
                    }

                barcode_obj = ProductBarcode.objects.filter(product_id=p.id).only("code").first()
                if barcode_obj and not products[p.id]["barcode"]:
                    products[p.id]["barcode"] = barcode_obj.code

                qty = int(item.quantity_units or 0)
                products[p.id]["markets"][str(market_id)] = {
                    "market_id": market_id,
                    "market_name": market_name,
                    "order_id": order.id,
                    "item_id": item.id,
                    "quantity_units": qty,
                    "notes": item.notes or "",
                }
                products[p.id]["total"] += qty

        markets_list = sorted(markets.values(), key=lambda x: (x["name"] or "").lower())
        products_list = sorted(products.values(), key=lambda x: (x["name"] or "").lower())

        return Response(
            {
                "provider_id": provider_id_int,
                "provider": provider_id,
                "provider_name": orders[0].provider.name if orders else "",
                "markets": markets_list,
                "products": products_list,
            },
            status=status.HTTP_200_OK,
        )

    @action(
        detail=False,
        methods=["post"],
        url_path="pivot-save",
        permission_classes=[permissions.IsAuthenticated, IsMasterUser],
    )
    @transaction.atomic
    def pivot_save(self, request):
        """
        Guarda una matriz pivot editada.

        Espera:
        {
          "provider_id": 1,
          "rows": [
            {
              "product_id": 10,
              "markets": {
                "7": 6,
                "1": 2
              }
            }
          ]
        }
        """
        provider_id = request.data.get("provider_id")
        rows = request.data.get("rows", [])

        if not provider_id:
            return Response(
                {"success": False, "detail": "provider_id es requerido."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not isinstance(rows, list):
            return Response(
                {"success": False, "detail": "rows debe ser una lista."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            provider_id = int(provider_id)
        except (TypeError, ValueError):
            return Response(
                {"success": False, "detail": "provider_id debe ser entero."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        order_map = {
            order.market_id: order
            for order in self.get_queryset()
            .filter(provider_id=provider_id)
            .select_related("market", "locked_by")
            .prefetch_related("items")
        }

        updated_cells = 0

        for row in rows:
            try:
                product_id = int(row.get("product_id"))
            except (TypeError, ValueError):
                continue

            markets_data = row.get("markets", {})
            if not isinstance(markets_data, dict):
                continue

            for market_id_raw, qty_raw in markets_data.items():
                try:
                    market_id = int(market_id_raw)
                    quantity_units = int(qty_raw or 0)
                except (TypeError, ValueError):
                    continue

                order = order_map.get(market_id)
                if not order:
                    continue

                order.clear_expired_lock()

                if order.locked_by and order.locked_by_id != request.user.id:
                    return Response(
                        {
                            "success": False,
                            "detail": "El pedido de la tienda {} está bloqueado por {}.".format(
                                order.market.name if order.market else market_id,
                                order.locked_by.username,
                            ),
                        },
                        status=status.HTTP_409_CONFLICT,
                    )

                existing_item = order.items.filter(product_id=product_id).first()

                if quantity_units <= 0:
                    if existing_item:
                        existing_item.delete()
                        updated_cells += 1
                    continue

                if existing_item:
                    existing_item.quantity_units = quantity_units
                    existing_item.purchase_unit = existing_item.purchase_unit or "boxes"
                    existing_item.save(update_fields=["quantity_units", "purchase_unit", "updated_at"])
                    updated_cells += 1
                else:
                    PurchaseOrderItem.objects.create(
                        order=order,
                        product_id=product_id,
                        quantity_units=quantity_units,
                        purchase_unit="boxes",
                        notes="",
                    )
                    updated_cells += 1

        return Response(
            {
                "success": True,
                "message": "Pivot guardado correctamente.",
                "updated_cells": updated_cells,
            },
            status=status.HTTP_200_OK,
        )

    def _build_grouped_preview_payload(self, orders):
        provider = orders[0].provider
        provider_name = provider.name if provider else ""
        provider_email = provider.email.strip() if provider and provider.email else ""
        provider_id = provider.id if provider else None

        orders_payload = []
        totals_by_market = []
        total_lines = 0
        total_units = 0

        consolidated_products = defaultdict(
            lambda: {
                "product_id": None,
                "product_name": "",
                "markets": {},
                "total_units": 0,
            }
        )

        for order in orders:
            market_name = order.market.name if order.market else "Sin tienda"
            market_id = order.market.id if order.market else None

            order_items_payload = []
            order_units = 0

            for item in order.items.all():
                product_name = item.product.name if item.product else "Producto"
                quantity_units = int(item.quantity_units or 0)

                order_items_payload.append(
                    {
                        "item_id": item.id,
                        "product_id": item.product_id,
                        "product_name": product_name,
                        "quantity_units": quantity_units,
                        "purchase_unit": item.purchase_unit,
                        "notes": item.notes or "",
                    }
                )

                key = str(item.product_id)
                consolidated_products[key]["product_id"] = item.product_id
                consolidated_products[key]["product_name"] = product_name
                consolidated_products[key]["markets"][str(market_id)] = {
                    "market_id": market_id,
                    "market_name": market_name,
                    "quantity_units": quantity_units,
                    "order_id": order.id,
                    "item_id": item.id,
                }
                consolidated_products[key]["total_units"] += quantity_units

                order_units += quantity_units
                total_units += quantity_units
                total_lines += 1

            orders_payload.append(
                {
                    "order_id": order.id,
                    "market_id": market_id,
                    "market_name": market_name,
                    "status": order.status,
                    "notes": order.notes or "",
                    "created_at": order.created_at,
                    "updated_at": order.updated_at,
                    "sent": bool(order.sent_at),
                    "sent_at": order.sent_at,
                    "sent_to_email": order.sent_to_email,
                    "items": order_items_payload,
                    "total_lines": len(order_items_payload),
                    "total_units": order_units,
                }
            )

            totals_by_market.append(
                {
                    "market_id": market_id,
                    "market_name": market_name,
                    "total_lines": len(order_items_payload),
                    "total_units": order_units,
                    "order_id": order.id,
                }
            )

        consolidated_rows = sorted(
            consolidated_products.values(),
            key=lambda row: row["product_name"].lower(),
        )

        return {
            "provider_id": provider_id,
            "provider_name": provider_name,
            "provider_email": provider_email,
            "orders_count": len(orders),
            "orders": orders_payload,
            "totals": {
                "lines": total_lines,
                "units": total_units,
            },
            "totals_by_market": totals_by_market,
            "consolidated_products": consolidated_rows,
        }

    def _normalize_grouped_send_payload(self, request):
        """
        Soporta dos formatos:
        1) antiguo:
           {"order_ids": [1,2,3]}
        2) premium:
           {
             "provider_id": 1,
             "attach_grouped_summary": true,
             "attach_individual_orders": true,
             "orders": [
               {
                 "order_id": 12,
                 "notes": "texto",
                 "items": [
                   {
                     "product_id": 5,
                     "quantity_units": 8,
                     "purchase_unit": "boxes",
                     "notes": "..."
                   }
                 ]
               }
             ]
           }
        """
        data = request.data or {}

        attach_grouped_summary = bool(data.get("attach_grouped_summary", True))
        attach_individual_orders = bool(data.get("attach_individual_orders", True))
        send_format = data.get("format", "both")

        raw_orders = data.get("orders")
        raw_order_ids = data.get("order_ids")

        if raw_orders and isinstance(raw_orders, list):
            try:
                normalized_orders = []
                for entry in raw_orders:
                    order_id = int(entry.get("order_id"))
                    items = entry.get("items", []) or []

                    normalized_items = []
                    for item in items:
                        product_id = int(item.get("product_id"))
                        quantity_units = int(item.get("quantity_units", 0) or 0)
                        if quantity_units <= 0:
                            continue

                        normalized_items.append(
                            {
                                "product_id": product_id,
                                "quantity_units": quantity_units,
                                "purchase_unit": item.get("purchase_unit") or "boxes",
                                "notes": item.get("notes") or "",
                            }
                        )

                    normalized_orders.append(
                        {
                            "order_id": order_id,
                            "notes": entry.get("notes") or "",
                            "items": normalized_items,
                        }
                    )

                return {
                    "mode": "edited_orders",
                    "provider_id": data.get("provider_id"),
                    "orders": normalized_orders,
                    "order_ids": [entry["order_id"] for entry in normalized_orders],
                    "attach_grouped_summary": attach_grouped_summary,
                    "attach_individual_orders": attach_individual_orders,
                    "send_format": send_format,
                }
            except Exception:
                raise ValueError("El payload 'orders' no tiene el formato correcto.")

        if not isinstance(raw_order_ids, list) or not raw_order_ids:
            raise ValueError("Debes enviar 'order_ids' o 'orders'.")

        try:
            normalized_ids = [int(x) for x in raw_order_ids]
        except (TypeError, ValueError):
            raise ValueError("Todos los 'order_ids' deben ser enteros.")

        return {
            "mode": "order_ids_only",
            "provider_id": data.get("provider_id"),
            "orders": [],
            "order_ids": normalized_ids,
            "attach_grouped_summary": attach_grouped_summary,
            "attach_individual_orders": attach_individual_orders,
        }

    def _apply_grouped_edits_to_orders(self, orders, edited_orders_payload, acting_user):
        """
        Persiste las correcciones premium antes de exportar/enviar.
        """
        orders_by_id = {order.id: order for order in orders}

        for payload in edited_orders_payload:
            order = orders_by_id.get(payload["order_id"])
            if not order:
                raise ValueError("Pedido no encontrado: {}".format(payload["order_id"]))

            if order.is_locked and order.locked_by_id and order.locked_by_id != acting_user.id:
                raise ValueError(
                    "El pedido #{} está bloqueado por {}.".format(
                        order.id,
                        order.locked_by.username,
                    )
                )

            order.notes = payload.get("notes", "") or ""
            order.save(update_fields=["notes", "updated_at"])

            items_payload = payload.get("items", []) or []

            consolidated = defaultdict(lambda: {"quantity_units": 0, "purchase_unit": "boxes", "notes": ""})

            for item in items_payload:
                product_id = int(item["product_id"])
                quantity_units = int(item["quantity_units"] or 0)
                purchase_unit = item.get("purchase_unit") or "boxes"
                notes = item.get("notes") or ""

                if quantity_units <= 0:
                    continue

                product_exists = Product.objects.filter(id=product_id).exists()
                if not product_exists:
                    raise ValueError("Producto no encontrado: {}".format(product_id))

                key = (product_id, purchase_unit)
                consolidated[key]["quantity_units"] += quantity_units
                consolidated[key]["purchase_unit"] = purchase_unit
                consolidated[key]["notes"] = notes

            order.items.all().delete()

            for (product_id, purchase_unit), item_data in consolidated.items():
                PurchaseOrderItem.objects.create(
                    order=order,
                    product_id=product_id,
                    quantity_units=item_data["quantity_units"],
                    purchase_unit=purchase_unit,
                    notes=item_data["notes"],
                )

        refreshed_orders = list(
            self.get_queryset()
            .filter(id__in=[order.id for order in orders])
            .select_related("provider", "market")
            .prefetch_related("items__product")
            .order_by("market__name", "created_at")
        )

        return refreshed_orders

    @action(detail=True, methods=["get"], url_path="export-excel")
    def export_excel(self, request, pk=None):
        """Exporta una orden de compra a Excel."""
        order = self.get_object()
        file_data = build_purchase_order_excel(order)

        response = HttpResponse(
            file_data.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = 'attachment; filename="pedido_{}.xlsx"'.format(order.id)
        return response

    @action(
        detail=False,
        methods=["get"],
        url_path="master-summary",
        permission_classes=[permissions.IsAuthenticated, IsMasterUser],
    )
    def master_summary(self, request):
        """
        Resumen master por mercados para un proveedor y una fecha.
        Devuelve una fila por market indicando si ha pedido o no.
        """
        date_str = request.query_params.get("date")
        provider_id = request.query_params.get("provider")

        if not provider_id:
            return Response(
                {"detail": "El parámetro 'provider' es requerido."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            provider_id_int = int(provider_id)
        except (TypeError, ValueError):
            return Response(
                {"detail": "El parámetro 'provider' debe ser un entero."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if date_str:
            try:
                selected_date = datetime.date.fromisoformat(date_str)
            except ValueError:
                return Response(
                    {"detail": "El parámetro 'date' no tiene el formato correcto (YYYY-MM-DD)."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            selected_date = timezone.now().date()

        markets = Market.objects.all().order_by("name")

        orders_qs = (
            self.get_queryset()
            .filter(
            .filter(
                provider_id=provider_id_int,
            ).filter(
                __import__("django.db.models", fromlist=["Q"]).Q(created_at__date=selected_date) | __import__("django.db.models", fromlist=["Q"]).Q(updated_at__date=selected_date)
            )
            .select_related("provider", "market", "locked_by")
            .prefetch_related("items")
            .order_by("-created_at")
        )

        orders_by_market = {}
        for order in orders_qs:
            order.clear_expired_lock(save=False)
            if order.market_id and order.market_id not in orders_by_market:
                orders_by_market[order.market_id] = order

        data = []
        for market in markets:
            order = orders_by_market.get(market.id)

            if order:
                data.append(
                    {
                        "market_id": market.id,
                        "market_name": market.name,
                        "has_order": True,
                        "order_id": order.id,
                        "provider_id": order.provider_id,
                        "provider_name": order.provider.name if order.provider else "",
                        "status": order.status,
                        "sent": bool(order.sent_at),
                        "sent_at": order.sent_at,
                        "sent_to_email": order.sent_to_email,
                        "total_items": order.items.count(),
                        "created_at": order.created_at,
                        "updated_at": order.updated_at,
                        "is_locked": order.is_locked,
                        "locked_by": order.locked_by_id,
                        "locked_by_username": order.locked_by.username if order.locked_by else "",
                        "lock_expires_at": order.lock_expires_at,
                        "ordered_by_username": order.ordered_by.username if order.ordered_by else "",
                    }
                )
            else:
                data.append(
                    {
                        "market_id": market.id,
                        "market_name": market.name,
                        "has_order": False,
                        "order_id": None,
                        "provider_id": provider_id_int,
                        "provider_name": "",
                        "status": None,
                        "sent": False,
                        "sent_at": None,
                        "sent_to_email": "",
                        "total_items": 0,
                        "created_at": None,
                        "updated_at": None,
                        "is_locked": False,
                        "locked_by": None,
                        "locked_by_username": "",
                        "lock_expires_at": None,
                    }
                )

        return Response(data, status=status.HTTP_200_OK)

    @action(
        detail=False,
        methods=["post"],
        url_path="preview-grouped",
        permission_classes=[permissions.IsAuthenticated, IsMasterUser],
    )
    def preview_grouped(self, request):
        """
        Previsualiza varios pedidos del mismo proveedor sin enviarlos.
        """
        order_ids = request.data.get("order_ids", [])

        if not isinstance(order_ids, list) or not order_ids:
            return Response(
                {"success": False, "detail": "Debes enviar 'order_ids' como lista no vacía."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            normalized_ids = [int(x) for x in order_ids]
        except (TypeError, ValueError):
            return Response(
                {"success": False, "detail": "Todos los 'order_ids' deben ser enteros."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        orders = list(
            self.get_queryset()
            .filter(id__in=normalized_ids)
            .select_related("provider", "market")
            .prefetch_related("items__product")
            .order_by("market__name", "created_at")
        )

        if not orders:
            return Response(
                {"success": False, "detail": "No se encontraron pedidos para previsualizar."},
                status=status.HTTP_404_NOT_FOUND,
            )

        found_ids = {order.id for order in orders}
        missing_ids = [oid for oid in normalized_ids if oid not in found_ids]
        if missing_ids:
            return Response(
                {
                    "success": False,
                    "detail": "No se encontraron estos pedidos: {}".format(", ".join(map(str, missing_ids))),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        provider_ids = {order.provider_id for order in orders}
        if len(provider_ids) > 1:
            return Response(
                {"success": False, "detail": "Solo puedes previsualizar juntos pedidos del mismo proveedor."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        payload = self._build_grouped_preview_payload(orders)

        return Response(
            {
                "success": True,
                "preview": payload,
            },
            status=status.HTTP_200_OK,
        )

    @action(
        detail=True,
        methods=["post"],
        url_path="send-to-provider",
        permission_classes=[permissions.IsAuthenticated, IsMasterUser],
    )
    def send_to_provider(self, request, pk=None):
        """Envía la orden al proveedor por email con Excel y PDF adjuntos."""
        order = self.get_object()

        try:
            recipient = self._send_single_order_email(order, request.user)

            return Response(
                {
                    "success": True,
                    "message": "Pedido enviado correctamente a {}".format(recipient),
                    "order_id": order.id,
                    "provider": order.provider.name if order.provider else "",
                    "email": recipient,
                },
                status=status.HTTP_200_OK,
            )

        except ValueError as exc:
            return Response(
                {"success": False, "detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        except Exception as exc:
            return Response(
                {
                    "success": False,
                    "detail": "Error enviando email al proveedor: {}".format(str(exc)),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(
        detail=False,
        methods=["post"],
        url_path="send-grouped",
        permission_classes=[permissions.IsAuthenticated, IsMasterUser],
    )
    @transaction.atomic
    def send_grouped(self, request):
        """
        Envía varios pedidos del mismo proveedor en un único correo.
        Premium:
        - puede recibir order_ids
        - o recibir orders editados y persistirlos antes de enviar
        - adjunta consolidado Excel/PDF
        - opcionalmente adjunta también los individuales
        """
        try:
            normalized = self._normalize_grouped_send_payload(request)
        except ValueError as exc:
            return Response(
                {"success": False, "detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        order_ids = normalized["order_ids"]

        orders = list(
            self.get_queryset()
            .filter(id__in=order_ids)
            .select_related("provider", "market", "locked_by")
            .prefetch_related("items__product")
            .order_by("market__name", "created_at")
        )

        if not orders:
            return Response(
                {"success": False, "detail": "No se encontraron pedidos para enviar."},
                status=status.HTTP_404_NOT_FOUND,
            )

        found_ids = {order.id for order in orders}
        missing_ids = [oid for oid in order_ids if oid not in found_ids]
        if missing_ids:
            return Response(
                {
                    "success": False,
                    "detail": "No se encontraron estos pedidos: {}".format(", ".join(map(str, missing_ids))),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        provider_ids = {order.provider_id for order in orders}
        if len(provider_ids) > 1:
            return Response(
                {"success": False, "detail": "Solo puedes enviar juntos pedidos del mismo proveedor."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        provider = orders[0].provider
        if not provider:
            return Response(
                {"success": False, "detail": "Los pedidos no tienen proveedor asociado."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not provider.email:
            return Response(
                {"success": False, "detail": "El proveedor no tiene email configurado."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        provider_id_from_payload = normalized.get("provider_id")
        if provider_id_from_payload and int(provider_id_from_payload) != provider.id:
            return Response(
                {"success": False, "detail": "El provider_id del payload no coincide con los pedidos enviados."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        for order in orders:
            order.clear_expired_lock()
            if order.locked_by and order.locked_by_id != request.user.id:
                return Response(
                    {
                        "success": False,
                        "detail": "El pedido #{} está bloqueado por {}.".format(order.id, order.locked_by.username),
                    },
                    status=status.HTTP_409_CONFLICT,
                )

        try:
            if normalized["mode"] == "edited_orders":
                orders = self._apply_grouped_edits_to_orders(
                    orders=orders,
                    edited_orders_payload=normalized["orders"],
                    acting_user=request.user,
                )

            recipient = provider.email.strip()
            provider_name = provider.name or "Proveedor"
            contact_name = provider.contact_person or provider_name

            stores_text = "\n".join(
                [
                    "- {} (pedido #{})".format(
                        order.market.name if order.market else "Sin tienda",
                        order.id,
                    )
                    for order in orders
                ]
            )

            body = (
                "Hola {},\n\n"
                "Adjuntamos un envío agrupado de pedidos para el proveedor {}.\n\n"
                "Pedidos incluidos:\n"
                "{}\n\n"
                "Total pedidos: {}\n\n"
                "Saludos,\n"
                "Kacha Digital BCN"
            ).format(
                contact_name,
                provider_name,
                stores_text,
                len(orders),
            )

            subject = "Pedidos agrupados - {} - {} tienda(s)".format(provider_name, len(orders))

            email = EmailMessage(
                subject=subject,
                body=body,
                to=[recipient],
            )

            if normalized["attach_grouped_summary"]:
                fmt = normalized.get("send_format", "both")
                slug = provider_name.replace(" ", "_")
                if fmt in ("both", "excel"):
                    grouped_excel = build_grouped_purchase_order_excel(orders)
                    email.attach(
                        "pedido_consolidado_{}.xlsx".format(slug),
                        grouped_excel.getvalue(),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                if fmt in ("both", "pdf"):
                    grouped_pdf = build_grouped_purchase_order_pdf(orders)
                    email.attach(
                        "pedido_consolidado_{}.pdf".format(slug),
                        grouped_pdf.getvalue(),
                        "application/pdf",
                    )
            email.send(fail_silently=False)

            for order in orders:
                self._mark_order_as_sent(order, recipient, request.user)

            return Response(
                {
                    "success": True,
                    "message": "Envío agrupado realizado correctamente a {}".format(recipient),
                    "provider": provider_name,
                    "email": recipient,
                    "orders_sent": [order.id for order in orders],
                    "stores": [
                        order.market.name if order.market else "Sin tienda"
                        for order in orders
                    ],
                    "mode": normalized["mode"],
                    "attach_grouped_summary": normalized["attach_grouped_summary"],
                    "attach_individual_orders": normalized["attach_individual_orders"],
                },
                status=status.HTTP_200_OK,
            )

        except ValueError as exc:
            return Response(
                {"success": False, "detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as exc:
            return Response(
                {
                    "success": False,
                    "detail": "Error enviando el grupo de pedidos: {}".format(str(exc)),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(
        detail=True,
        methods=["post"],
        url_path="lock",
        permission_classes=[permissions.IsAuthenticated, IsMasterUser],
    )
    def lock_order(self, request, pk=None):
        """Bloquea un pedido para edición."""
        order = self.get_object()
        order.clear_expired_lock()

        if order.locked_by and order.locked_by_id != request.user.id:
            return Response(
                {
                    "success": False,
                    "detail": "Este pedido está siendo editado por {}.".format(order.locked_by.username),
                    "locked_by": order.locked_by.username,
                    "locked_at": order.locked_at,
                    "lock_expires_at": order.lock_expires_at,
                },
                status=status.HTTP_409_CONFLICT,
            )

        try:
            order.lock(request.user)
            serializer = self.get_serializer(order)
            return Response(
                {
                    "success": True,
                    "message": "Pedido bloqueado correctamente.",
                    "order": serializer.data,
                },
                status=status.HTTP_200_OK,
            )
        except Exception as exc:
            return Response(
                {"success": False, "detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(
        detail=True,
        methods=["post"],
        url_path="unlock",
        permission_classes=[permissions.IsAuthenticated, IsMasterUser],
    )
    def unlock_order(self, request, pk=None):
        """Libera el bloqueo del pedido."""
        order = self.get_object()
        order.clear_expired_lock()

        if not order.locked_by:
            serializer = self.get_serializer(order)
            return Response(
                {
                    "success": True,
                    "message": "El pedido ya estaba desbloqueado.",
                    "order": serializer.data,
                },
                status=status.HTTP_200_OK,
            )

        if order.locked_by_id != request.user.id:
            return Response(
                {
                    "success": False,
                    "detail": "Solo {} puede liberar este bloqueo.".format(order.locked_by.username),
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        order.unlock(request.user)
        serializer = self.get_serializer(order)
        return Response(
            {
                "success": True,
                "message": "Pedido desbloqueado correctamente.",
                "order": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["get"], url_path="has-ordered-today")
    def has_ordered_today(self, request):
        """Retorna si el usuario actual ha creado al menos una orden hoy."""
        today = timezone.now().date()
        qs = PurchaseOrder.objects.filter(
            ordered_by=request.user,
            created_at__date=today,
        )

        provider_id = request.query_params.get("provider")
        if provider_id is not None:
            try:
                provider_id_int = int(provider_id)
            except (TypeError, ValueError):
                return Response(
                    {"detail": "El parámetro 'provider' debe ser un entero."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            qs = qs.filter(provider_id=provider_id_int)

        return Response({"has_ordered_today": qs.exists()})

    @action(detail=False, methods=["get"], url_path="by-day")
    def by_day(self, request):
        """Lista órdenes por día exacto usando ?date=YYYY-MM-DD."""
        date_str = request.query_params.get("date")
        if not date_str:
            return Response(
                {"detail": "El parámetro 'date' es requerido."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            selected_date = datetime.date.fromisoformat(date_str)
        except ValueError:
            return Response(
                {"detail": "El parámetro 'date' no tiene el formato correcto (YYYY-MM-DD)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        base_qs = self.get_queryset().filter(
            created_at__date=selected_date,
            status=PurchaseOrder.Status.DRAFT,
        )

        provider_id = request.query_params.get("provider")
        if provider_id is not None:
            try:
                provider_id_int = int(provider_id)
            except (TypeError, ValueError):
                return Response(
                    {"detail": "El parámetro 'provider' debe ser un entero."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            base_qs = base_qs.filter(provider_id=provider_id_int)

        queryset = self.filter_queryset(base_qs.order_by("-created_at"))

        if not queryset.exists():
            return Response(
                {"detail": "No existen órdenes para el día seleccionado."},
                status=status.HTTP_200_OK,
            )

        obj = queryset.first()
        serializer = self.get_serializer(obj)
        return Response(serializer.data)

    @action(detail=False, methods=["post"], url_path="received-products")
    def received_products(self, request):
        """
        Recibe una lista de productos recibidos y devuelve los productos
        de la última orden SHIPPED del usuario autenticado para un proveedor.
        """
        provider_id = request.query_params.get("provider")
        if provider_id is None:
            return Response(
                {"detail": "El parámetro 'provider' es requerido."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            provider_id_int = int(provider_id)
        except (TypeError, ValueError):
            return Response(
                {"detail": "El parámetro 'provider' debe ser un entero."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        po_qs = (
            self.get_queryset()
            .filter(
                status=PurchaseOrder.Status.SHIPPED,
                ordered_by=request.user,
                provider_id=provider_id_int,
            )
            .order_by("-updated_at", "-created_at")
        )

        if not po_qs.exists():
            return Response(
                {"detail": "No existen órdenes enviadas para este proveedor."},
                status=status.HTTP_200_OK,
            )

        po = po_qs.first()

        payload_list = request.data.get("products", []) or []
        if not isinstance(payload_list, (list, tuple)):
            return Response(
                {"detail": "El cuerpo debe incluir 'products' como lista."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        received_ids = set()

        for entry in payload_list:
            product_id = None

            if isinstance(entry, int):
                product_id = entry
            elif isinstance(entry, str):
                try:
                    product_id = int(entry)
                except (TypeError, ValueError):
                    barcode = ProductBarcode.objects.filter(code=entry).only("product_id").first()
                    if barcode:
                        product_id = barcode.product_id

            if product_id is not None:
                received_ids.add(int(product_id))

        items = (
            PurchaseOrderItem.objects.select_related("product")
            .filter(order=po)
            .order_by("product__name")
        )

        result = []
        for item in items:
            product_id = item.product_id
            is_received = product_id in received_ids

            result.append(
                {
                    "id": product_id,
                    "name": item.product.name,
                    "quantity_units": item.quantity_units,
                    "received": is_received,
                    "missing": not is_received,
                }
            )

        return Response(result, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path="last-shipped")
    def last_shipped(self, request):
        """Devuelve la última orden en estado SHIPPED."""
        qs = self.get_queryset().filter(
            status=PurchaseOrder.Status.SHIPPED,
            ordered_by=request.user,
        )

        provider_id = request.query_params.get("provider")
        if provider_id is not None:
            try:
                provider_id_int = int(provider_id)
            except (TypeError, ValueError):
                return Response(
                    {"detail": "El parámetro 'provider' debe ser un entero."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            qs = qs.filter(provider_id=provider_id_int)

        qs = qs.order_by("-updated_at", "-created_at")

        if not qs.exists():
            return Response(
                {"detail": "No existen órdenes enviadas."},
                status=status.HTTP_200_OK,
            )

        obj = qs.first()
        serializer = self.get_serializer(obj)
        return Response(serializer.data)


class PurchaseOrderItemViewSet(
    OrganizationQuerySetMixin,
    OrganizationPermissionMixin,
    viewsets.ModelViewSet,
):
    """ViewSet para items de órdenes de compra con filtrado automático por organización."""

    queryset = PurchaseOrderItem.objects.select_related("order", "product").all()
    serializer_class = PurchaseOrderItemSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "post", "put", "patch", "head", "options"]
    organization_field_path = "order__market__organization"
