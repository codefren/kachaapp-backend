"""Admin configuration for purchase orders."""

from django.contrib import admin
from django.urls import path, reverse
from django.template.response import TemplateResponse
from django.utils.timezone import make_aware
from datetime import datetime
from django.db.models import Q
from simple_history.admin import SimpleHistoryAdmin
from proveedores.models import Provider

from .models import PurchaseOrder, PurchaseOrderItem


class PurchaseOrderItemInline(admin.TabularInline):
    """Inline admin for purchase order items."""
    
    model = PurchaseOrderItem
    extra = 1
    fields = ("product", "quantity_units", "purchase_unit", "notes")
    autocomplete_fields = ("product",)


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(SimpleHistoryAdmin):
    """Admin configuration for PurchaseOrder model."""
    
    list_display = ("id", "provider", "status", "ordered_by", "created_at")
    list_filter = ("provider", "status", "created_at")
    search_fields = ("provider__name", "ordered_by__username")
    inlines = [PurchaseOrderItemInline]
    autocomplete_fields = ("provider", "ordered_by")
    ordering = ("-created_at",)
    actions = ("mark_as_draft", "mark_as_placed", "mark_as_received", "mark_as_canceled")

    # Custom admin view: Pivot unidades por producto x tienda
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path("pivot/", self.admin_site.admin_view(self.pivot_view), name="purchaseorder_pivot"),
        ]
        return custom_urls + urls

    def pivot_view(self, request):
        # Filtros
        provider_id = request.GET.get("provider")
        date_from = request.GET.get("date_from")
        date_to = request.GET.get("date_to")
        markets = request.GET.getlist("market")  # puede repetirse

        context = dict(
            self.admin_site.each_context(request),
            title="Resumen de pedidos por tiendas",
            opts=self.model._meta,
            app_label=self.model._meta.app_label,
        )

        if not provider_id:
            context.update({
                "error": "Seleccione un proveedor (?provider=<id>) para ver el pivot.",
            })
            return TemplateResponse(request, "admin/purchase_orders/purchaseorder/pivot.html", context)

        try:
            provider_id = int(provider_id)
        except Exception:
            context.update({"error": "El parámetro provider debe ser un entero."})
            return TemplateResponse(request, "admin/purchase_orders/purchaseorder/pivot.html", context)
        # Nombre del proveedor
        provider_obj = Provider.objects.filter(id=provider_id).only("name").first()
        context["provider_name"] = provider_obj.name if provider_obj else f"Proveedor {provider_id}"

        # Solo órdenes con estado IN_PROCESS
        in_process_statuses = [getattr(PurchaseOrder.Status, "IN_PROCESS", None)]
        in_process_statuses = [s for s in in_process_statuses if s is not None]

        # Queryset base de líneas
        items_qs = (
            PurchaseOrderItem.objects.select_related("order", "order__provider", "order__market", "product")
            .filter(order__provider_id=provider_id, order__status__in=in_process_statuses)
        )

        # Filtro por fechas (created_at de la PO)
        def parse_date(val):
            try:
                return make_aware(datetime.fromisoformat(val))
            except Exception:
                return None
        if date_from:
            dt = parse_date(date_from)
            if dt:
                items_qs = items_qs.filter(order__created_at__gte=dt)
        if date_to:
            dt = parse_date(date_to)
            if dt:
                items_qs = items_qs.filter(order__created_at__lte=dt)

        # Filtro por markets (ids)
        if markets:
            # limpiar ids válidos
            try:
                market_ids = [int(m) for m in markets if int(m) > 0]
                if market_ids:
                    items_qs = items_qs.filter(order__market_id__in=market_ids)
            except Exception:
                pass

        # Construcción de columnas (markets) y filas (products)
        markets_list = []
        markets_seen = set()
        products_list = []
        products_seen = set()

        # Índice (product_id, market_id) -> (order_id, quantity_units, order_created_at)
        cell_map = {}

        for it in items_qs.order_by("product__name", "order__market__name", "-order__created_at"):
            m = it.order.market
            p = it.product
            if m and m.id not in markets_seen:
                markets_seen.add(m.id)
                markets_list.append({"id": m.id, "name": m.name})
            if p and p.id not in products_seen:
                products_seen.add(p.id)
                products_list.append({"id": p.id, "name": p.name})

            key = (p.id if p else None, m.id if m else None)
            if key[0] is None or key[1] is None:
                continue
            # Mantener la PO más reciente para la celda
            existing = cell_map.get(key)
            cur_tuple = (it.order.id, it.quantity_units, it.order.created_at)
            if not existing or cur_tuple[2] > existing[2]:
                cell_map[key] = cur_tuple

        # Orden alfabético por nombres para una tabla estable
        markets_list.sort(key=lambda x: x["name"] or "")
        products_list.sort(key=lambda x: x["name"] or "")

        # Construir filas para template (entries por market con market_id)
        rows = []
        for prod in products_list:
            row = {"product": prod, "entries": [], "total": 0}
            for mk in markets_list:
                key = (prod["id"], mk["id"])
                cell = cell_map.get(key)
                if cell:
                    order_id, qty, _created = cell
                    url = reverse("admin:purchase_orders_purchaseorder_change", args=[order_id])
                    entry = {"market_id": mk["id"], "cell": {"qty": qty, "order_id": order_id, "url": url}}
                    try:
                        row["total"] += int(qty or 0)
                    except Exception:
                        pass
                else:
                    entry = {"market_id": mk["id"], "cell": None}
                row["entries"].append(entry)
            rows.append(row)

        context.update({
            "provider_id": provider_id,
            "markets": markets_list,
            "rows": rows,
            "filters": {
                "date_from": date_from or "",
                "date_to": date_to or "",
                "status": ",".join(in_process_statuses),
            },
        })

        return TemplateResponse(request, "admin/purchase_orders/purchaseorder/pivot.html", context)

    @admin.action(description="Mark selected orders as Draft")
    def mark_as_draft(self, request, queryset):
        """Mark selected orders as Draft."""
        updated = queryset.update(status="DRAFT")
        self.message_user(request, f"{updated} orders marked as Draft")

    @admin.action(description="Mark selected orders as Placed")
    def mark_as_placed(self, request, queryset):
        """Mark selected orders as Placed."""
        updated = queryset.update(status="PLACED")
        self.message_user(request, f"{updated} orders marked as Placed")

    @admin.action(description="Mark selected orders as Received")
    def mark_as_received(self, request, queryset):
        """Mark selected orders as Received."""
        updated = queryset.update(status="RECEIVED")
        self.message_user(request, f"{updated} orders marked as Received")

    @admin.action(description="Mark selected orders as Canceled")
    def mark_as_canceled(self, request, queryset):
        """Mark selected orders as Canceled."""
        updated = queryset.update(status="CANCELED")
        self.message_user(request, f"{updated} orders marked as Canceled")


@admin.register(PurchaseOrderItem)
class PurchaseOrderItemAdmin(admin.ModelAdmin):
    """Admin configuration for PurchaseOrderItem model."""
    
    list_display = (
        "id",
        "order",
        "product",
        "quantity_units",
        "purchase_unit",
        "created_at",
    )
    list_filter = ("order", "product", "created_at")
    search_fields = (
        "product__name",
        "product__sku",
        "order__provider__name",
        "order__ordered_by__username",
    )
    autocomplete_fields = ("order", "product")
    ordering = ("-created_at",)
    list_select_related = ("order", "product")
