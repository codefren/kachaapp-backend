"""Views for receiving products and barcode search within purchase orders."""

from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import transaction
from decimal import Decimal, InvalidOperation
from datetime import date as date_cls, time as time_cls, datetime
from django.db.models import Q

from purchase_orders.serializers import PurchaseOrderSerializer
from proveedores.models import Product, ProductBarcode
from purchase_orders.models import PurchaseOrder, PurchaseOrderItem
from received.models import ReceivedProduct, Reception
from received.serializers import InvoiceImageUploadSerializer, ReceptionSerializer
from market.models import LoginHistory
import re


def parse_12hour_time(time_str):
    """
    Convierte tiempo en formato 12 horas (HH:MM AM/PM) a objeto time de 24 horas.
    
    Formatos aceptados:
    - "2:30 PM", "02:30 PM", "14:30"
    - "10:15 AM", "10:15 am", "22:15"
    
    Returns:
        time object en formato 24 horas
    Raises:
        ValueError: si el formato no es válido
    """
    if not time_str or not isinstance(time_str, str):
        raise ValueError("Time string is required")
    
    time_str = time_str.strip()
    
    # Patrón para formato 12 horas: HH:MM AM/PM (case insensitive)
    pattern_12h = r'^(\d{1,2}):(\d{2})\s*(AM|PM)$'
    match = re.match(pattern_12h, time_str.upper())
    
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2))
        period = match.group(3)
        
        # Validaciones básicas
        if hour < 1 or hour > 12:
            raise ValueError("Hour must be between 1 and 12 for 12-hour format")
        if minute < 0 or minute > 59:
            raise ValueError("Minutes must be between 0 and 59")
        
        # Convertir a formato 24 horas
        if period == 'AM':
            if hour == 12:
                hour = 0  # 12:XX AM = 00:XX
        else:  # PM
            if hour != 12:
                hour += 12  # 1:XX PM = 13:XX, pero 12:XX PM = 12:XX
        
        return time_cls(hour, minute)
    
    # Si no coincide con formato 12h, intentar formato 24h como fallback
    try:
        return time_cls.fromisoformat(time_str)
    except ValueError:
        raise ValueError(
            "Invalid time format. Use 'HH:MM AM/PM' (e.g., '2:30 PM') or 'HH:MM' (24-hour format)"
        )


class SearchReceivedProductViewSet(viewsets.ModelViewSet):
    """Keep search functionality intact: validate barcode within a purchase order and return product info."""

    queryset = PurchaseOrder.objects.all()
    serializer_class = PurchaseOrderSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "head", "options", "post"]

    def _get_user_market(self, user):
        """Return latest market from user's LoginHistory or None."""
        last = (
            LoginHistory.objects.select_related("market")
            .filter(user=user)
            .order_by("-timestamp")
            .first()
        )
        if not last:
            return None
        return last.market

    @action(detail=True, methods=["get"], url_path="by-barcode")
    def by_barcode(self, request, pk=None):
        barcode = request.query_params.get("barcode")
        name = request.query_params.get("name")
        purchase_order_id = pk

        if not barcode and not name:
            return Response(
                {"detail": "Provide either 'barcode' or 'name' as query parameter."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Verify purchase order exists
        try:
            purchase_order = self.queryset.get(id=purchase_order_id)
        except PurchaseOrder.DoesNotExist:
            return Response(
                {"detail": f"Purchase order #{purchase_order_id} not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Resolve product either by barcode or by name within this purchase order
        product = None
        if barcode:
            # Find product by barcode
            try:
                product_barcode = ProductBarcode.objects.select_related("product").get(
                    code=barcode
                )
                product = product_barcode.product
            except ProductBarcode.DoesNotExist:
                return Response(
                    {"detail": f"No product found with barcode '{barcode}'."},
                    status=status.HTTP_404_NOT_FOUND,
                )
        else:
            # Find by product name within the purchase order
            name_matches = (
                PurchaseOrderItem.objects.select_related("product")
                .filter(order=purchase_order, product__name__icontains=name)
            )
            count = name_matches.count()
            if count == 0:
                return Response(
                    {"detail": f"No product found with name containing '{name}'."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            if count > 1:
                return Response(
                    {"detail": f"Multiple products match the name '{name}'. Please refine your search."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            product = name_matches.first().product

        # Verify product is in the purchase order and get item
        try:
            order_item = PurchaseOrderItem.objects.select_related("product").get(
                order=purchase_order,
                product=product,
            )
        except PurchaseOrderItem.DoesNotExist:
            return Response(
                {
                    "detail": f"Product '{product.name}' with barcode '{barcode}' is not in purchase order #{purchase_order_id}."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = {
            "purchase_order_id": purchase_order.id,
            "provider_name": purchase_order.provider.name,
            "product_id": product.id,
            "product_name": product.name,
            # Build absolute HTTPS image URL (mirror of serializer get_image logic)
            "image": (lambda: (
                (lambda img_field: (
                    (lambda: (
                        (lambda url: (
                            (lambda abs_url: (
                                ("https://" + abs_url[len("http://"):]) if abs_url.startswith("http://") else abs_url
                            ))(request.build_absolute_uri(url) if request is not None else url)
                        ))(img_field.url)
                    ))() if img_field else None
                ))(getattr(product, "image", None))
            ))(),
            "product_sku": getattr(product, "sku", None),
            "barcode_scanned": barcode,
            "quantity_ordered": order_item.quantity_units,
            "purchase_unit": order_item.purchase_unit,
        }

        return Response(result)

    @action(detail=True, methods=["get", "post"], url_path="received")
    def received(self, request, pk=None):
        """GET: list received records for this purchase order and user's market.
        POST: create received records (batch) and return the reception id.
        Market is always inferred from user's latest LoginHistory.
        """
        # Ensure purchase order exists
        try:
            purchase_order = self.queryset.get(id=pk)
        except PurchaseOrder.DoesNotExist:
            return Response(
                {"detail": f"Purchase order #{pk} not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Resolve market from user's login history
        market = self._get_user_market(request.user)
        if not market:
            return Response(
                {"detail": "No market found for current user (no login history)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # POST - create reception batch
        items = request.data.get("items")
        if not isinstance(items, list) or not items:
            return Response(
                {"detail": "Field 'items' must be a non-empty list."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        reception = Reception.objects.create(
            purchase_order=purchase_order,
            market=market,
            received_by=request.user if not request.user.is_anonymous else None,
        )

        created = []
        for idx, item in enumerate(items, start=1):
            product = None
            barcode = item.get("barcode")
            product_id = item.get("product_id")
            qty = item.get("quantity_received")
            is_damaged = bool(item.get("is_damaged", False))
            notes = item.get("notes", "")

            # basic validations
            if not (barcode or product_id) or (barcode and product_id):
                return Response(
                    {"detail": f"Item #{idx}: provide either 'product_id' or 'barcode' (exclusively)."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            try:
                qty = int(qty)
            except (TypeError, ValueError):
                return Response(
                    {"detail": f"Item #{idx}: 'quantity_received' must be an integer."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if qty < 0:
                return Response(
                    {"detail": f"Item #{idx}: 'quantity_received' must be greater than or equal to 0."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # resolve product
            if product_id:
                try:
                    product = Product.objects.get(id=product_id)
                except Product.DoesNotExist:
                    return Response(
                        {"detail": f"Item #{idx}: product id {product_id} not found."},
                        status=status.HTTP_404_NOT_FOUND,
                    )
            else:
                try:
                    pb = ProductBarcode.objects.select_related("product").get(code=barcode)
                    product = pb.product
                except ProductBarcode.DoesNotExist:
                    return Response(
                        {"detail": f"Item #{idx}: no product found with barcode '{barcode}'."},
                        status=status.HTTP_404_NOT_FOUND,
                    )

            # verify product belongs to PO and get ordered quantity/unit
            try:
                poi = PurchaseOrderItem.objects.get(order=purchase_order, product=product)
            except PurchaseOrderItem.DoesNotExist:
                return Response(
                    {"detail": f"Item #{idx}: product '{product.name}' is not in purchase order #{purchase_order.id}."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Los flags de estado se calculan automáticamente en el modelo
            rp = ReceivedProduct(
                purchase_order=purchase_order,
                product=product,
                market=market,
                reception=reception,
                barcode_scanned=barcode or "",
                quantity_received=qty,
                is_damaged=is_damaged,
                notes=notes,
                received_by=request.user if not request.user.is_anonymous else None,
            )
            rp.save()
            created.append(rp.id)

        return Response({"reception_id": reception.id}, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="received-extra")
    def received_extra(self, request, pk=None):
        """POST: Register ONE extra product not in the purchase order.
        Returns product info similar to by-barcode endpoint.
        """
        # Ensure purchase order exists
        try:
            purchase_order = self.queryset.get(id=pk)
        except PurchaseOrder.DoesNotExist:
            return Response(
                {"detail": f"Purchase order #{pk} not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Resolve market from user's login history
        market = self._get_user_market(request.user)
        if not market:
            return Response(
                {"detail": "No market found for current user (no login history)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Extract and validate payload for single product
        product_id = request.data.get("product_id")
        barcode = request.data.get("barcode")
        quantity_received = request.data.get("quantity_received")
        is_damaged = request.data.get("is_damaged", False)
        notes = request.data.get("notes", "")
        reason = request.data.get("reason", "OTHER")

        # Basic validations
        if not (barcode or product_id) or (barcode and product_id):
            return Response(
                {"detail": "Provide either 'product_id' or 'barcode' (exclusively)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            quantity_received = int(quantity_received)
        except (TypeError, ValueError):
            return Response(
                {"detail": "'quantity_received' must be an integer."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if quantity_received < 0:
            return Response(
                {"detail": "'quantity_received' must be greater than or equal to 0."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Resolve product by ID or barcode
        product = None
        if product_id:
            try:
                product = Product.objects.get(id=product_id)
            except Product.DoesNotExist:
                return Response(
                    {"detail": f"Product id {product_id} not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )
        else:
            try:
                pb = ProductBarcode.objects.select_related("product").get(code=barcode)
                product = pb.product
            except ProductBarcode.DoesNotExist:
                return Response(
                    {"detail": f"No product found with barcode '{barcode}'."},
                    status=status.HTTP_404_NOT_FOUND,
                )

        # Get or create reception for this purchase order and market
        reception, created = Reception.objects.get_or_create(
            purchase_order=purchase_order,
            market=market,
            defaults={
                'received_by': request.user if not request.user.is_anonymous else None,
            }
        )

        # Create ReceivedProduct with is_not_in_order=True
        received_product = ReceivedProduct.objects.create(
            purchase_order=purchase_order,
            product=product,
            market=market,
            reception=reception,
            barcode_scanned=barcode or "",
            quantity_received=quantity_received,
            is_damaged=is_damaged,
            notes=notes,
            is_not_in_order=True,  # Always True for this endpoint
            reason_extra=reason,
            received_by=request.user if not request.user.is_anonymous else None,
        )

        # Build response similar to by-barcode endpoint
        result = {
            "purchase_order_id": purchase_order.id,
            "provider_name": purchase_order.provider.name,
            "product_id": product.id,
            "product_name": product.name,
            # Build absolute HTTPS image URL (mirror of serializer get_image logic)
            "image": (lambda: (
                (lambda img_field: (
                    (lambda: (
                        (lambda url: (
                            (lambda abs_url: (
                                ("https://" + abs_url[len("http://"):]) if abs_url.startswith("http://") else abs_url
                            ))(request.build_absolute_uri(url) if request is not None else url)
                        ))(img_field.url)
                    ))() if img_field else None
                ))(getattr(product, "image", None))
            ))(),
            "product_sku": getattr(product, "sku", None),
            "barcode_scanned": barcode,
            "quantity_ordered": 0,  # Always 0 for extra products (not in order)
            "purchase_unit": "units",  # Default unit for extra products
            "amount_miss": 0,  # Always 0 (product was not expected)
            "amount_boxes": getattr(product, "amount_boxes", 0),
        }

        return Response(result, status=status.HTTP_201_CREATED)


class ReceptionViewSet(viewsets.ViewSet):
    """Gestiona recepciones: detalle y edición (status e items)."""

    permission_classes = [permissions.IsAuthenticated]

    def _get_user_market(self, user):
        last = (
            LoginHistory.objects.select_related("market")
            .filter(user=user)
            .order_by("-timestamp")
            .first()
        )
        if not last:
            return None
        return last.market

    def retrieve(self, request, pk=None):
        try:
            reception = Reception.objects.select_related("purchase_order", "market").get(id=pk)
        except Reception.DoesNotExist:
            return Response({"detail": "Reception not found."}, status=status.HTTP_404_NOT_FOUND)

        market = self._get_user_market(request.user)
        if not market:
            return Response(
                {"detail": "No market found for current user (no login history)."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if reception.market_id != market.id:
            return Response({"detail": "Reception not available for user's market."}, status=status.HTTP_403_FORBIDDEN)

        items = (
            ReceivedProduct.objects.select_related("product")
            .filter(reception=reception)
            .order_by("-received_at")
        )
        data = {
            "id": reception.id,
            "purchase_order_id": reception.purchase_order_id,
            "market_id": reception.market_id,
            "status": reception.status,
            "created_at": reception.created_at,
            "invoice_image_url": request.build_absolute_uri(reception.invoice_image.url) if reception.invoice_image else None,
            "invoice_date": reception.invoice_date,
            "invoice_time": reception.invoice_time,
            "invoice_total": str(reception.invoice_total) if reception.invoice_total is not None else None,
            "items": [
                {
                    "id": r.id,
                    "product_id": r.product_id,
                    "product_name": r.product.name,
                    "image": (r.product.image.url if getattr(r.product, "image", None) else None),
                    "barcode_scanned": r.barcode_scanned,
                    "quantity_received": r.quantity_received,
                    "is_damaged": r.is_damaged,
                    "is_missing": r.is_missing,
                    "is_over_received": r.is_over_received,
                    "is_under_received": r.is_under_received,
                    "is_not_in_order": r.is_not_in_order,
                    "reason_extra": r.reason_extra,
                    "notes": r.notes,
                    "received_at": r.received_at,
                }
                for r in items
            ],
        }
        return Response(data)

    def list(self, request):
        """GET: lista de recepciones del market del usuario con solo id e imagen de factura."""
        market = self._get_user_market(request.user)
        if not market:
            return Response(
                {"detail": "No market found for current user (no login history)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        qs = (
            Reception.objects
            .filter(market=market)
            .only("id", "invoice_image", "created_at")
            .order_by("-created_at")
        )
        data = [
            {
                "id": r.id,
                "invoice_image_url": request.build_absolute_uri(r.invoice_image.url) if r.invoice_image else None,
            }
            for r in qs
        ]
        return Response(data)

    @action(detail=False, methods=["get"], url_path="completed")
    def completed(self, request):
        market = self._get_user_market(request.user)
        if not market:
            return Response(
                {"detail": "No market found for current user (no login history)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        date_str = request.query_params.get("date")
        invoice_date_str = request.query_params.get("invoice_date")
        provider_str = request.query_params.get("provider")
        filter_date = None
        filter_invoice_date = None
        provider_id = None
        if date_str:
            try:
                filter_date = date_cls.fromisoformat(str(date_str))
            except Exception:
                return Response(
                    {"detail": "Query param 'date' must be ISO date YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        if provider_str is not None:
            try:
                provider_id = int(provider_str)
                if provider_id <= 0:
                    raise ValueError
            except Exception:
                return Response(
                    {"detail": "Query param 'provider' must be a positive integer."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        if invoice_date_str:
            try:
                filter_invoice_date = date_cls.fromisoformat(str(invoice_date_str))
            except Exception:
                return Response(
                    {"detail": "Query param 'invoice_date' must be ISO date YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        qs = (
            Reception.objects
            .filter(market=market, status=Reception.Status.COMPLETED)
        )

        if filter_date:
            qs = qs.filter(created_at__date=filter_date)

        if filter_invoice_date:
            qs = qs.filter(invoice_date=filter_invoice_date)

        if provider_id is not None:
            qs = qs.filter(purchase_order__provider_id=provider_id)

        qs = qs.only("id", "invoice_image", "created_at", "invoice_date").order_by("-created_at")
        data = [
            {
                "id": r.id,
                "invoice_image_url": request.build_absolute_uri(r.invoice_image.url) if r.invoice_image else None,
            }
            for r in qs
        ]
        return Response(data)

    def partial_update(self, request, pk=None):
        """PATCH: actualizar status y/o reemplazar todos los items."""
        try:
            reception = Reception.objects.select_related("purchase_order", "market").get(id=pk)
        except Reception.DoesNotExist:
            return Response({"detail": "Reception not found."}, status=status.HTTP_404_NOT_FOUND)

        market = self._get_user_market(request.user)
        if not market:
            return Response(
                {"detail": "No market found for current user (no login history)."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if reception.market_id != market.id:
            return Response({"detail": "Reception not available for user's market."}, status=status.HTTP_403_FORBIDDEN)

        new_status = request.data.get("status")
        items = request.data.get("items", None)
        inv_image = request.FILES.get("invoice_image", None)
        inv_date = request.data.get("invoice_date", None)
        inv_time = request.data.get("invoice_time", None)
        inv_total = request.data.get("invoice_total", None)

        if items is not None and reception.status != Reception.Status.DRAFT:
            return Response({"detail": "Only DRAFT receptions can replace items."}, status=status.HTTP_400_BAD_REQUEST)

        if items is not None and not isinstance(items, list):
            return Response({"detail": "Field 'items' must be a list."}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            update_fields = []
            if new_status in (Reception.Status.DRAFT, Reception.Status.COMPLETED):
                reception.status = new_status
                update_fields.append("status")

            # Handle invoice fields updates independently
            if inv_image is not None:
                reception.invoice_image = inv_image
                update_fields.append("invoice_image")

            if inv_date is not None:
                if inv_date in ("", None):
                    reception.invoice_date = None
                else:
                    try:
                        reception.invoice_date = date_cls.fromisoformat(str(inv_date))
                    except Exception:
                        return Response({"detail": "Field 'invoice_date' must be ISO date YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)
                update_fields.append("invoice_date")

            if inv_time is not None:
                if inv_time in ("", None):
                    reception.invoice_time = None
                else:
                    try:
                        reception.invoice_time = parse_12hour_time(str(inv_time))
                    except ValueError as e:
                        return Response(
                            {"detail": f"Field 'invoice_time' error: {str(e)}"}, 
                            status=status.HTTP_400_BAD_REQUEST
                        )
                    except Exception:
                        return Response(
                            {"detail": "Field 'invoice_time' must be in format 'HH:MM AM/PM' (e.g., '2:30 PM')."}, 
                            status=status.HTTP_400_BAD_REQUEST
                        )
                update_fields.append("invoice_time")

            if inv_total is not None:
                if inv_total in ("", None):
                    reception.invoice_total = None
                else:
                    try:
                        dec = Decimal(str(inv_total))
                    except (InvalidOperation, TypeError, ValueError):
                        return Response({"detail": "Field 'invoice_total' must be a decimal number."}, status=status.HTTP_400_BAD_REQUEST)
                    if dec < 0:
                        return Response({"detail": "Field 'invoice_total' must be greater than or equal to 0."}, status=status.HTTP_400_BAD_REQUEST)
                    reception.invoice_total = dec
                update_fields.append("invoice_total")

            if update_fields:
                reception.save(update_fields=update_fields)

            if items is not None:
                ReceivedProduct.objects.filter(reception=reception).delete()

                for idx, item in enumerate(items, start=1):
                    product = None
                    barcode = item.get("barcode")
                    product_id = item.get("product_id")
                    qty = item.get("quantity_received")
                    is_damaged = bool(item.get("is_damaged", False))
                    notes = item.get("notes", "")

                    if not (barcode or product_id) or (barcode and product_id):
                        return Response(
                            {"detail": f"Item #{idx}: provide either 'product_id' or 'barcode' (exclusively)."},
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                    try:
                        qty = int(qty)
                    except (TypeError, ValueError):
                        return Response(
                            {"detail": f"Item #{idx}: 'quantity_received' must be an integer."},
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                    if qty < 0:
                        return Response(
                            {"detail": f"Item #{idx}: 'quantity_received' must be greater than or equal to 0."},
                            status=status.HTTP_400_BAD_REQUEST,
                        )

                    if product_id:
                        try:
                            product = Product.objects.get(id=product_id)
                        except Product.DoesNotExist:
                            return Response(
                                {"detail": f"Item #{idx}: product id {product_id} not found."},
                                status=status.HTTP_404_NOT_FOUND,
                            )
                    else:
                        try:
                            pb = ProductBarcode.objects.select_related("product").get(code=barcode)
                            product = pb.product
                        except ProductBarcode.DoesNotExist:
                            return Response(
                                {"detail": f"Item #{idx}: no product found with barcode '{barcode}'."},
                                status=status.HTTP_404_NOT_FOUND,
                            )

                    try:
                        poi = PurchaseOrderItem.objects.get(order=reception.purchase_order, product=product)
                    except PurchaseOrderItem.DoesNotExist:
                        return Response(
                            {"detail": f"Item #{idx}: product '{product.name}' is not in purchase order #{reception.purchase_order.id}."},
                            status=status.HTTP_400_BAD_REQUEST,
                        )

                    # Los flags de estado se calculan automáticamente en el modelo
                    ReceivedProduct.objects.create(
                        purchase_order=reception.purchase_order,
                        product=product,
                        market=reception.market,
                        reception=reception,
                        barcode_scanned=barcode or "",
                        quantity_received=qty,
                        is_damaged=is_damaged,
                        notes=notes,
                        received_by=request.user if not request.user.is_anonymous else None,
                    )

        return Response({"reception_id": reception.id, "status": reception.status})

    @action(detail=True, methods=["post"], url_path="upload-invoice")
    def upload_invoice(self, request, pk=None):
        """POST: subir imagen de factura y datos opcionales."""
        try:
            reception = Reception.objects.select_related("market").get(id=pk)
        except Reception.DoesNotExist:
            return Response({"detail": "Reception not found."}, status=status.HTTP_404_NOT_FOUND)

        market = self._get_user_market(request.user)
        if not market:
            return Response(
                {"detail": "No market found for current user (no login history)."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if reception.market_id != market.id:
            return Response({"detail": "Reception not available for user's market."}, status=status.HTTP_403_FORBIDDEN)

        serializer = InvoiceImageUploadSerializer(data=request.data)
        if serializer.is_valid():
            # Actualizar la recepción con los datos de la factura
            reception.invoice_image = serializer.validated_data['invoice_image']
            
            if 'invoice_date' in serializer.validated_data:
                reception.invoice_date = serializer.validated_data['invoice_date']
            
            if 'invoice_time' in serializer.validated_data:
                reception.invoice_time = serializer.validated_data['invoice_time']
                
            if 'invoice_total' in serializer.validated_data:
                reception.invoice_total = serializer.validated_data['invoice_total']
            
            reception.save()
            
            # Devolver la recepción actualizada
            response_serializer = ReceptionSerializer(reception, context={'request': request})
            return Response(response_serializer.data, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
