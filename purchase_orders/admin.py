"""Admin configuration for purchase orders."""

import datetime
from collections import defaultdict

from django.contrib import admin, messages
from django.db import transaction
from django.http import HttpResponse, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.timezone import make_aware, now

from simple_history.admin import SimpleHistoryAdmin

from proveedores.models import Provider

from .export_utils import (
    build_purchase_order_excel,
    build_purchase_order_pdf,
    build_grouped_purchase_order_excel,
    build_grouped_purchase_order_pdf,
)
from .models import PurchaseOrder, PurchaseOrderItem


class PurchaseOrderItemInline(admin.TabularInline):
    model = PurchaseOrderItem
    extra = 1
    fields = ("product", "quantity_units", "purchase_unit", "notes")
    autocomplete_fields = ("product",)


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(SimpleHistoryAdmin):
    list_display = (
        "id",
        "quick_actions",
        "provider",
        "market",
        "status",
        "ordered_by",
        "sent_at",
        "sent_to_email",
        "sent_by",
        "created_at",
    )
    list_filter = (
        "provider",
        "market",
        "status",
        "created_at",
        "sent_at",
    )
    search_fields = (
        "provider__name",
        "market__name",
        "ordered_by__username",
        "sent_to_email",
        "sent_by__username",
        "notes",
    )
    inlines = [PurchaseOrderItemInline]
    autocomplete_fields = ("provider", "market", "ordered_by", "sent_by")
    ordering = ("-created_at",)
    actions = (
        "mark_as_draft",
        "mark_as_placed",
        "mark_as_received",
        "mark_as_canceled",
        "send_selected_orders",
        "export_selected_excel",
        "export_selected_pdf",
        "merge_selected_orders",
    )
    readonly_fields = (
        "created_at",
        "updated_at",
        "sent_at",
        "sent_to_email",
        "sent_by",
    )
    fields = (
        "provider",
        "market",
        "ordered_by",
        "status",
        "notes",
        "sent_at",
        "sent_to_email",
        "sent_by",
        "created_at",
        "updated_at",
    )

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "consolidar/",
                self.admin_site.admin_view(self.consolidar_view),
                name="purchaseorder_consolidar",
            ),
            path(
                "pivot/",
                self.admin_site.admin_view(self.pivot_view),
                name="purchaseorder_pivot",
            ),
            path(
                "merge-preview/",
                self.admin_site.admin_view(self.merge_preview_view),
                name="purchaseorder_merge_preview",
            ),
            path(
                "<int:order_id>/export-excel/",
                self.admin_site.admin_view(self.export_excel_admin),
                name="purchaseorder_export_excel",
            ),
            path(
                "<int:order_id>/export-pdf/",
                self.admin_site.admin_view(self.export_pdf_admin),
                name="purchaseorder_export_pdf",
            ),
            path(
                "<int:order_id>/send-email/",
                self.admin_site.admin_view(self.send_email_admin),
                name="purchaseorder_send_email",
            ),
        ]
        return custom_urls + urls

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["pivot_url"] = reverse("admin:purchaseorder_pivot")
        extra_context["pivot_button_label"] = "Resumen por tiendas"
        extra_context["consolidar_url"] = reverse("admin:purchaseorder_consolidar")
        return super().changelist_view(request, extra_context=extra_context)

    def quick_actions(self, obj):
        change_url = reverse("admin:purchase_orders_purchaseorder_change", args=[obj.pk])
        excel_url = reverse("admin:purchaseorder_export_excel", args=[obj.pk])
        pdf_url = reverse("admin:purchaseorder_export_pdf", args=[obj.pk])
        send_url = reverse("admin:purchaseorder_send_email", args=[obj.pk])
        return format_html(
            '<a style="background:#2563eb;color:white;padding:4px 8px;border-radius:6px;margin-right:4px;text-decoration:none;" href="{}">Editar</a>'
            '<a style="background:#16a34a;color:white;padding:4px 8px;border-radius:6px;margin-right:4px;text-decoration:none;" href="{}">Excel</a>'
            '<a style="background:#ea580c;color:white;padding:4px 8px;border-radius:6px;margin-right:4px;text-decoration:none;" href="{}">PDF</a>'
            '<a style="background:#10b981;color:white;padding:4px 8px;border-radius:6px;text-decoration:none;" href="{}">Enviar</a>',
            change_url, excel_url, pdf_url, send_url,
        )

    quick_actions.short_description = "Acciones"

    def export_excel_admin(self, request, order_id):
        order = (
            PurchaseOrder.objects.select_related("provider", "market", "ordered_by")
            .prefetch_related("items__product")
            .get(pk=order_id)
        )
        file_data = build_purchase_order_excel(order)
        return self._build_excel_response(file_data, order.id)

    def export_pdf_admin(self, request, order_id):
        order = (
            PurchaseOrder.objects.select_related("provider", "market", "ordered_by")
            .prefetch_related("items__product")
            .get(pk=order_id)
        )
        file_data = build_purchase_order_pdf(order)
        return self._build_pdf_response(file_data, order.id)

    def send_email_admin(self, request, order_id):
        order = PurchaseOrder.objects.select_related("provider", "market", "ordered_by").get(pk=order_id)
        if not order.provider:
            self.message_user(request, "La orden no tiene proveedor asociado.", level=messages.ERROR)
            return HttpResponseRedirect(request.META.get("HTTP_REFERER", ".."))
        if not order.provider.email:
            self.message_user(request, "Proveedor sin email", level=messages.ERROR)
            return HttpResponseRedirect(request.META.get("HTTP_REFERER", ".."))
        try:
            from django.core.mail import EmailMessage
            excel_file = build_purchase_order_excel(order)
            pdf_file = build_purchase_order_pdf(order)
            email = EmailMessage(
                subject=f"Pedido #{order.id}",
                body="Adjuntamos el pedido en Excel y PDF.",
                to=[order.provider.email.strip()],
            )
            email.attach(
                f"pedido_{order.id}.xlsx",
                excel_file.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            email.attach(
                f"pedido_{order.id}.pdf",
                pdf_file.getvalue(),
                "application/pdf",
            )
            email.send(fail_silently=False)
            order.sent_at = now()
            order.sent_to_email = order.provider.email.strip()
            order.sent_by = request.user
            if order.status == PurchaseOrder.Status.PLACED:
                order.status = PurchaseOrder.Status.IN_PROCESS
            order.save(update_fields=["sent_at", "sent_to_email", "sent_by", "status", "updated_at"])
            self.message_user(request, "Pedido enviado correctamente.", level=messages.SUCCESS)
        except Exception as exc:
            self.message_user(request, f"Error enviando pedido: {exc}", level=messages.ERROR)
        return HttpResponseRedirect(request.META.get("HTTP_REFERER", ".."))

    def _build_excel_response(self, file_data, order_id):
        response = HttpResponse(
            file_data.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="pedido_{order_id}.xlsx"'
        return response

    def _build_pdf_response(self, file_data, order_id):
        response = HttpResponse(
            file_data.getvalue(),
            content_type="application/pdf",
        )
        response["Content-Disposition"] = f'attachment; filename="pedido_{order_id}.pdf"'
        return response

    def consolidar_view(self, request):
        from django.core.mail import EmailMessage as DjangoEmailMessage

        context = dict(
            self.admin_site.each_context(request),
            title="Consolidar y enviar pedidos",
            opts=self.model._meta,
            app_label=self.model._meta.app_label,
        )

        all_providers = Provider.objects.order_by("name")
        context["all_providers"] = all_providers

        provider_id_raw = request.GET.get("provider_id") or request.POST.get("provider_id")
        date_filter = request.GET.get("date_filter", "today")
        context["date_filter"] = date_filter

        selected_provider_id = None
        provider_email = None

        if provider_id_raw:
            try:
                selected_provider_id = int(provider_id_raw)
            except (ValueError, TypeError):
                selected_provider_id = None

        context["selected_provider_id"] = selected_provider_id

        if not selected_provider_id:
            return TemplateResponse(
                request,
                "admin/purchase_orders/purchaseorder/consolidar_pedidos.html",
                context,
            )

        provider = Provider.objects.filter(id=selected_provider_id).first()
        if not provider:
            messages.error(request, "Proveedor no encontrado.")
            return TemplateResponse(
                request,
                "admin/purchase_orders/purchaseorder/consolidar_pedidos.html",
                context,
            )

        provider_email = provider.email.strip() if provider.email else None
        context["provider_email"] = provider_email

        qs = PurchaseOrder.objects.filter(provider_id=selected_provider_id)
        today = now().date()

        if date_filter == "today":
            qs = qs.filter(created_at__date=today)
        elif date_filter == "week":
            qs = qs.filter(created_at__date__gte=today - datetime.timedelta(days=7))
        elif date_filter == "month":
            qs = qs.filter(created_at__date__gte=today - datetime.timedelta(days=30))

        qs = (
            qs.select_related("market", "provider")
            .prefetch_related("items__product")
            .order_by("market__name", "created_at")
        )

        order_list = list(qs)

        if not order_list:
            context["orders"] = []
            return TemplateResponse(
                request,
                "admin/purchase_orders/purchaseorder/consolidar_pedidos.html",
                context,
            )

        orders_meta = []
        market_order_map = {}

        for order in order_list:
            market_name = order.market.name if order.market else "Sin tienda"
            orders_meta.append({
                "order_id": order.id,
                "market_name": market_name,
                "status": order.status,
            })
            market_order_map[market_name] = order

        grouped = {}
        product_meta = {}

        for order in order_list:
            market_name = order.market.name if order.market else "Sin tienda"
            for item in order.items.all():
                if not item.product:
                    continue
                pname = item.product.name
                pid = item.product_id
                sku = getattr(item.product, "sku", "") or ""
                if pname not in product_meta:
                    product_meta[pname] = {"product_id": pid, "sku": sku}
                    grouped[pname] = {}
                grouped[pname][market_name] = grouped[pname].get(market_name, 0) + int(item.quantity_units or 0)

        market_names = [o["market_name"] for o in orders_meta]
        rows = []
        totals_by_col = [0] * len(market_names)
        grand_total = 0

        for pname in sorted(grouped.keys()):
            meta = product_meta[pname]
            cells = []
            row_total = 0
            for i, market_name in enumerate(market_names):
                order = market_order_map.get(market_name)
                qty = grouped[pname].get(market_name, 0)
                cells.append({
                    "order_id": order.id if order else None,
                    "qty": qty,
                })
                totals_by_col[i] += qty
                row_total += qty
                grand_total += qty
            rows.append({
                "product_id": meta["product_id"],
                "product_name": pname,
                "sku": meta["sku"],
                "cells": cells,
                "total": row_total,
            })

        context.update({
            "orders": orders_meta,
            "rows": rows,
            "totals_row": totals_by_col,
            "grand_total": grand_total,
            "included_orders": [o["order_id"] for o in orders_meta],
        })

        if request.method == "POST":
            action = request.POST.get("action", "save")

            included_ids = set()
            for order in order_list:
                key = f"include_order_{order.id}"
                if request.POST.get(key):
                    included_ids.add(order.id)

            context["included_orders"] = included_ids

            updates = {}
            for key, value in request.POST.items():
                if key.startswith("qty_"):
                    parts = key.split("_")
                    if len(parts) == 3:
                        try:
                            product_id = int(parts[1])
                            order_id = int(parts[2])
                            qty = int(value or 0)
                            if order_id not in updates:
                                updates[order_id] = {}
                            updates[order_id][product_id] = qty
                        except (ValueError, TypeError):
                            continue

            try:
                with transaction.atomic():
                    for order in order_list:
                        if order.id not in updates:
                            continue
                        for product_id, qty in updates[order.id].items():
                            if qty > 0:
                                item, created = PurchaseOrderItem.objects.get_or_create(
                                    order=order,
                                    product_id=product_id,
                                    defaults={
                                        "quantity_units": qty,
                                        "purchase_unit": "boxes",
                                        "notes": "",
                                    },
                                )
                                if not created:
                                    item.quantity_units = qty
                                    item.save(update_fields=["quantity_units", "updated_at"])
                            else:
                                PurchaseOrderItem.objects.filter(
                                    order=order, product_id=product_id
                                ).delete()
                messages.success(request, "✅ Cambios guardados correctamente.")
            except Exception as exc:
                messages.error(request, f"❌ Error guardando cambios: {exc}")
                url = reverse("admin:purchaseorder_consolidar")
                return HttpResponseRedirect(
                    f"{url}?provider_id={selected_provider_id}&date_filter={date_filter}"
                )

            selected_orders = list(
                PurchaseOrder.objects.select_related("provider", "market")
                .prefetch_related("items__product")
                .filter(id__in=included_ids)
                .order_by("market__name", "created_at")
            )

            if not selected_orders and action in ("download_excel", "download_pdf", "send"):
                messages.warning(request, "⚠ No hay tiendas seleccionadas.")
                url = reverse("admin:purchaseorder_consolidar")
                return HttpResponseRedirect(
                    f"{url}?provider_id={selected_provider_id}&date_filter={date_filter}"
                )

            attach_excel = bool(request.POST.get("attach_excel"))
            attach_pdf = bool(request.POST.get("attach_pdf"))
            attach_individual = bool(request.POST.get("attach_individual"))
            slug = provider.name.replace(" ", "_")

            if action == "download_excel":
                try:
                    file_data = build_grouped_purchase_order_excel(selected_orders)
                    response = HttpResponse(
                        file_data.getvalue(),
                        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                    response["Content-Disposition"] = f'attachment; filename="consolidado_{slug}.xlsx"'
                    return response
                except Exception as exc:
                    messages.error(request, f"❌ Error generando Excel: {exc}")

            elif action == "download_pdf":
                try:
                    file_data = build_grouped_purchase_order_pdf(selected_orders)
                    response = HttpResponse(file_data.getvalue(), content_type="application/pdf")
                    response["Content-Disposition"] = f'attachment; filename="consolidado_{slug}.pdf"'
                    return response
                except Exception as exc:
                    messages.error(request, f"❌ Error generando PDF: {exc}")

            elif action == "send":
                if not provider_email:
                    messages.error(request, "❌ El proveedor no tiene email configurado.")
                else:
                    try:
                        provider_name = provider.name or "Proveedor"
                        contact_name = getattr(provider, "contact_person", None) or provider_name
                        stores_text = "\n".join([
                            "- {} (pedido #{})".format(
                                o.market.name if o.market else "Sin tienda", o.id
                            )
                            for o in selected_orders
                        ])
                        body = (
                            "Hola {},\n\nAdjuntamos los pedidos consolidados para {}.\n\n"
                            "Tiendas incluidas:\n{}\n\nTotal tiendas: {}\n\nSaludos,\nKacha Digital BCN"
                        ).format(contact_name, provider_name, stores_text, len(selected_orders))
                        email = DjangoEmailMessage(
                            subject="Pedidos consolidados - {} - {} tienda(s)".format(
                                provider_name, len(selected_orders)
                            ),
                            body=body,
                            to=[provider_email],
                        )
                        if attach_excel:
                            grouped_excel = build_grouped_purchase_order_excel(selected_orders)
                            email.attach(
                                f"consolidado_{slug}.xlsx",
                                grouped_excel.getvalue(),
                                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            )
                        if attach_pdf:
                            grouped_pdf = build_grouped_purchase_order_pdf(selected_orders)
                            email.attach(
                                f"consolidado_{slug}.pdf",
                                grouped_pdf.getvalue(),
                                "application/pdf",
                            )
                        if attach_individual:
                            for o in selected_orders:
                                market_slug = (
                                    o.market.name.replace(" ", "_").replace("/", "_")
                                    if o.market and o.market.name else "sin_tienda"
                                )
                                excel_file = build_purchase_order_excel(o)
                                pdf_file = build_purchase_order_pdf(o)
                                email.attach(
                                    f"pedido_{o.id}_{market_slug}.xlsx",
                                    excel_file.getvalue(),
                                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                )
                                email.attach(
                                    f"pedido_{o.id}_{market_slug}.pdf",
                                    pdf_file.getvalue(),
                                    "application/pdf",
                                )
                        email.send(fail_silently=False)
                        for o in selected_orders:
                            o.sent_at = now()
                            o.sent_to_email = provider_email
                            o.sent_by = request.user
                            if o.status in (PurchaseOrder.Status.DRAFT, PurchaseOrder.Status.PLACED):
                                o.status = PurchaseOrder.Status.IN_PROCESS
                            o.save(update_fields=["sent_at", "sent_to_email", "sent_by", "status", "updated_at"])
                        messages.success(
                            request,
                            f"✉ Pedidos enviados correctamente a {provider_email}. Estado actualizado a IN_PROCESS."
                        )
                    except Exception as exc:
                        messages.error(request, f"❌ Error enviando email: {exc}")

            url = reverse("admin:purchaseorder_consolidar")
            return HttpResponseRedirect(
                f"{url}?provider_id={selected_provider_id}&date_filter={date_filter}"
            )

        return TemplateResponse(
            request,
            "admin/purchase_orders/purchaseorder/consolidar_pedidos.html",
            context,
        )

    def pivot_view(self, request):
        provider_id = request.GET.get("provider")
        date_from = request.GET.get("date_from")
        date_to = request.GET.get("date_to")
        markets = request.GET.getlist("market")

        context = dict(
            self.admin_site.each_context(request),
            title="Resumen de pedidos por tiendas",
            opts=self.model._meta,
            app_label=self.model._meta.app_label,
        )

        if not provider_id:
            context.update({"error": "Seleccione un proveedor (?provider=<id>) para ver el resumen."})
            return TemplateResponse(request, "admin/purchase_orders/purchaseorder/pivot.html", context)

        try:
            provider_id = int(provider_id)
        except Exception:
            context.update({"error": "El parámetro provider debe ser un entero."})
            return TemplateResponse(request, "admin/purchase_orders/purchaseorder/pivot.html", context)

        provider_obj = Provider.objects.filter(id=provider_id).only("name").first()
        context["provider_name"] = provider_obj.name if provider_obj else f"Proveedor {provider_id}"

        items_qs = (
            PurchaseOrderItem.objects.select_related("order", "order__provider", "order__market", "product")
            .filter(order__provider_id=provider_id)
        )

        def parse_date(val):
            try:
                return make_aware(datetime.datetime.fromisoformat(val))
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
        if markets:
            try:
                market_ids = [int(m) for m in markets if int(m) > 0]
                if market_ids:
                    items_qs = items_qs.filter(order__market_id__in=market_ids)
            except Exception:
                pass

        markets_list = []
        markets_seen = set()
        products_list = []
        products_seen = set()
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
            existing = cell_map.get(key)
            cur_tuple = (it.order.id, it.quantity_units, it.order.created_at)
            if not existing or cur_tuple[2] > existing[2]:
                cell_map[key] = cur_tuple

        markets_list.sort(key=lambda x: x["name"] or "")
        products_list.sort(key=lambda x: x["name"] or "")

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
            "filters": {"date_from": date_from or "", "date_to": date_to or ""},
        })
        return TemplateResponse(request, "admin/purchase_orders/purchaseorder/pivot.html", context)

    def merge_preview_view(self, request):
        ids_param = request.GET.get("ids", "") or request.POST.get("ids", "")
        ids = [int(x) for x in ids_param.split(",") if x.strip().isdigit()]

        context = dict(
            self.admin_site.each_context(request),
            title="Unificación de pedidos seleccionados",
            opts=self.model._meta,
            app_label=self.model._meta.app_label,
        )

        if not ids:
            context["error"] = "No se han recibido pedidos seleccionados."
            return TemplateResponse(request, "admin/purchase_orders/purchaseorder/merge_preview.html", context)

        orders = list(
            PurchaseOrder.objects.select_related("provider", "market", "ordered_by")
            .prefetch_related("items__product")
            .filter(id__in=ids)
            .order_by("market__name", "created_at")
        )

        if not orders:
            context["error"] = "No se encontraron pedidos."
            return TemplateResponse(request, "admin/purchase_orders/purchaseorder/merge_preview.html", context)

        provider_ids = {o.provider_id for o in orders}
        if len(provider_ids) > 1:
            context["error"] = "Solo puedes unir pedidos del mismo proveedor."
            return TemplateResponse(request, "admin/purchase_orders/purchaseorder/merge_preview.html", context)

        provider = orders[0].provider
        markets = []
        market_seen = set()
        market_order_map = {}

        for order in orders:
            market_name = order.market.name if order.market else "Sin market"
            if market_name not in market_seen:
                market_seen.add(market_name)
                markets.append(market_name)
            market_order_map[market_name] = order.id

        grouped = defaultdict(dict)
        product_ids = {}
        totals_by_market = defaultdict(int)
        grand_total = 0

        for order in orders:
            market_name = order.market.name if order.market else "Sin market"
            for item in order.items.all():
                product_name = item.product.name if item.product else f"Producto {item.product_id}"
                product_id = item.product_id
                product_ids[product_name] = product_id
                current = grouped[product_name].get(market_name, {"qty": 0, "product_id": product_id})
                current["qty"] += int(item.quantity_units or 0)
                grouped[product_name][market_name] = current
                totals_by_market[market_name] += int(item.quantity_units or 0)
                grand_total += int(item.quantity_units or 0)

        rows = []
        for product_name in sorted(grouped.keys()):
            product_id = product_ids.get(product_name)
            product_total = 0
            cells = []
            for market_name in markets:
                cell_data = grouped[product_name].get(market_name)
                qty = cell_data["qty"] if cell_data else 0
                order_id = market_order_map.get(market_name)
                product_total += qty
                cells.append({"market_name": market_name, "order_id": order_id, "qty": qty})
            rows.append({
                "product_id": product_id,
                "product_name": product_name,
                "cells": cells,
                "total": product_total,
            })

        if request.method == "POST":
            action = request.POST.get("action", "save")
            updates = defaultdict(dict)

            for key, value in request.POST.items():
                if key.startswith("qty_"):
                    parts = key.split("_")
                    if len(parts) == 3:
                        try:
                            product_id = int(parts[1])
                            order_id = int(parts[2])
                            qty = int(value or 0)
                            updates[order_id][product_id] = qty
                        except (ValueError, TypeError):
                            continue

            try:
                with transaction.atomic():
                    for order in orders:
                        if order.id not in updates:
                            continue
                        for product_id, qty in updates[order.id].items():
                            if qty > 0:
                                item, created = PurchaseOrderItem.objects.get_or_create(
                                    order=order,
                                    product_id=product_id,
                                    defaults={"quantity_units": qty, "purchase_unit": "boxes", "notes": ""},
                                )
                                if not created:
                                    item.quantity_units = qty
                                    item.save(update_fields=["quantity_units", "updated_at"])
                            else:
                                PurchaseOrderItem.objects.filter(
                                    order=order, product_id=product_id
                                ).delete()
                messages.success(request, "✅ Cambios guardados correctamente.")

                if action == "save_and_send":
                    if not provider or not provider.email:
                        messages.error(request, "❌ El proveedor no tiene email configurado.")
                    else:
                        try:
                            from django.core.mail import EmailMessage as DjangoEmailMessage
                            fresh_orders = list(
                                PurchaseOrder.objects.select_related("provider", "market")
                                .prefetch_related("items__product")
                                .filter(id__in=ids)
                                .order_by("market__name", "created_at")
                            )
                            recipient = provider.email.strip()
                            provider_name = provider.name or "Proveedor"
                            contact_name = getattr(provider, "contact_person", None) or provider_name
                            stores_text = "\n".join([
                                "- {} (pedido #{})".format(
                                    o.market.name if o.market else "Sin tienda", o.id
                                )
                                for o in fresh_orders
                            ])
                            body = (
                                "Hola {},\n\nAdjuntamos un envío agrupado de pedidos para el proveedor {}.\n\n"
                                "Pedidos incluidos:\n{}\n\nTotal pedidos: {}\n\nSaludos,\nKacha Digital BCN"
                            ).format(contact_name, provider_name, stores_text, len(fresh_orders))
                            email = DjangoEmailMessage(
                                subject="Pedidos agrupados - {} - {} tienda(s)".format(
                                    provider_name, len(fresh_orders)
                                ),
                                body=body,
                                to=[recipient],
                            )
                            slug = provider_name.replace(" ", "_")
                            grouped_excel = build_grouped_purchase_order_excel(fresh_orders)
                            grouped_pdf = build_grouped_purchase_order_pdf(fresh_orders)
                            email.attach(
                                f"pedido_consolidado_{slug}.xlsx",
                                grouped_excel.getvalue(),
                                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            )
                            email.attach(
                                f"pedido_consolidado_{slug}.pdf",
                                grouped_pdf.getvalue(),
                                "application/pdf",
                            )
                            for o in fresh_orders:
                                market_slug = (
                                    o.market.name.replace(" ", "_").replace("/", "_")
                                    if o.market and o.market.name else "sin_tienda"
                                )
                                excel_file = build_purchase_order_excel(o)
                                pdf_file = build_purchase_order_pdf(o)
                                email.attach(
                                    f"pedido_{o.id}_{market_slug}.xlsx",
                                    excel_file.getvalue(),
                                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                )
                                email.attach(
                                    f"pedido_{o.id}_{market_slug}.pdf",
                                    pdf_file.getvalue(),
                                    "application/pdf",
                                )
                            email.send(fail_silently=False)
                            for o in fresh_orders:
                                o.sent_at = now()
                                o.sent_to_email = recipient
                                o.sent_by = request.user
                                if o.status == PurchaseOrder.Status.PLACED:
                                    o.status = PurchaseOrder.Status.IN_PROCESS
                                o.save(update_fields=["sent_at", "sent_to_email", "sent_by", "status", "updated_at"])
                            messages.success(request, f"✉ Pedidos enviados correctamente a {recipient}.")
                        except Exception as exc:
                            messages.error(request, f"❌ Error enviando email: {exc}")

            except Exception as exc:
                messages.error(request, f"❌ Error guardando cambios: {exc}")

            url = reverse("admin:purchaseorder_merge_preview")
            return HttpResponseRedirect(f"{url}?ids={ids_param}")

        totals_row = [totals_by_market.get(m, 0) for m in markets]
        context.update({
            "provider": provider,
            "orders": orders,
            "markets": markets,
            "rows": rows,
            "totals_row": totals_row,
            "grand_total": grand_total,
            "ids_param": ids_param,
        })
        return TemplateResponse(
            request,
            "admin/purchase_orders/purchaseorder/merge_preview.html",
            context,
        )

    @admin.action(description="Mark selected orders as Draft")
    def mark_as_draft(self, request, queryset):
        updated = queryset.update(status="DRAFT")
        self.message_user(request, f"{updated} pedidos marcados como Draft")

    @admin.action(description="Mark selected orders as Placed")
    def mark_as_placed(self, request, queryset):
        updated = queryset.update(status="PLACED")
        self.message_user(request, f"{updated} pedidos marcados como Placed")

    @admin.action(description="Mark selected orders as Received")
    def mark_as_received(self, request, queryset):
        updated = queryset.update(status="RECEIVED")
        self.message_user(request, f"{updated} pedidos marcados como Received")

    @admin.action(description="Mark selected orders as Canceled")
    def mark_as_canceled(self, request, queryset):
        updated = queryset.update(status="CANCELED")
        self.message_user(request, f"{updated} pedidos marcados como Canceled")

    @admin.action(description="Enviar pedidos seleccionados por email")
    def send_selected_orders(self, request, queryset):
        from django.core.mail import EmailMessage
        ok = 0
        fail = 0
        for order in queryset:
            if not order.provider or not order.provider.email:
                fail += 1
                continue
            try:
                excel_file = build_purchase_order_excel(order)
                pdf_file = build_purchase_order_pdf(order)
                email = EmailMessage(
                    subject=f"Pedido #{order.id}",
                    body="Adjuntamos el pedido en Excel y PDF.",
                    to=[order.provider.email.strip()],
                )
                email.attach(
                    f"pedido_{order.id}.xlsx",
                    excel_file.getvalue(),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
                email.attach(
                    f"pedido_{order.id}.pdf",
                    pdf_file.getvalue(),
                    "application/pdf",
                )
                email.send(fail_silently=False)
                order.sent_at = now()
                order.sent_to_email = order.provider.email.strip()
                order.sent_by = request.user
                if order.status == PurchaseOrder.Status.PLACED:
                    order.status = PurchaseOrder.Status.IN_PROCESS
                order.save(update_fields=["sent_at", "sent_to_email", "sent_by", "status", "updated_at"])
                ok += 1
            except Exception:
                fail += 1
        self.message_user(request, f"Pedidos enviados: {ok}. Fallidos: {fail}.", level=messages.INFO)

    @admin.action(description="Exportar Excel del pedido seleccionado")
    def export_selected_excel(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(request, "Selecciona solo un pedido para exportar Excel.", level=messages.WARNING)
            return
        order = queryset.first()
        file_data = build_purchase_order_excel(order)
        return self._build_excel_response(file_data, order.id)

    @admin.action(description="Exportar PDF del pedido seleccionado")
    def export_selected_pdf(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(request, "Selecciona solo un pedido para exportar PDF.", level=messages.WARNING)
            return
        order = queryset.first()
        file_data = build_purchase_order_pdf(order)
        return self._build_pdf_response(file_data, order.id)

    @admin.action(description="Unir pedidos seleccionados")
    def merge_selected_orders(self, request, queryset):
        if queryset.count() < 2:
            self.message_user(request, "Selecciona al menos dos pedidos para unir.", level=messages.WARNING)
            return
        provider_ids = set(queryset.values_list("provider_id", flat=True))
        if len(provider_ids) > 1:
            self.message_user(request, "Solo puedes unir pedidos del mismo proveedor.", level=messages.ERROR)
            return
        ids = ",".join(str(pk) for pk in queryset.values_list("id", flat=True))
        url = reverse("admin:purchaseorder_merge_preview")
        return HttpResponseRedirect(f"{url}?ids={ids}")


@admin.register(PurchaseOrderItem)
class PurchaseOrderItemAdmin(admin.ModelAdmin):
    list_display = ("id", "order", "product", "quantity_units", "purchase_unit", "created_at")
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
