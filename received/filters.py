"""Filters for received products."""

import django_filters
from django.db.models import Q

from .models import ReceivedProduct


class ReceivedProductFilter(django_filters.FilterSet):
    """Filter for received products with barcode search."""

    barcode = django_filters.CharFilter(method="filter_by_barcode", label="Barcode")
    purchase_order = django_filters.NumberFilter(field_name="purchase_order_id", label="Purchase Order ID")
    product = django_filters.NumberFilter(field_name="product_id", label="Product ID")
    received_by = django_filters.NumberFilter(field_name="received_by_id", label="Received By User ID")
    is_damaged = django_filters.BooleanFilter(field_name="is_damaged", label="Is Damaged")
    is_missing = django_filters.BooleanFilter(field_name="is_missing", label="Is Missing")
    date_from = django_filters.DateFilter(field_name="received_at", lookup_expr="date__gte", label="Received From Date")
    date_to = django_filters.DateFilter(field_name="received_at", lookup_expr="date__lte", label="Received To Date")
    provider = django_filters.NumberFilter(method="filter_by_provider", label="Provider ID")

    class Meta:
        model = ReceivedProduct
        fields = [
            "barcode",
            "purchase_order",
            "product",
            "received_by",
            "is_damaged",
            "is_missing",
            "date_from",
            "date_to",
            "provider",
        ]

    def filter_by_barcode(self, queryset, name, value):
        """Filter by barcode - searches in barcode_scanned field and product barcodes."""
        if not value:
            return queryset
        
        from proveedores.models import ProductBarcode
        
        # Find products that have this barcode
        product_ids = ProductBarcode.objects.filter(
            code__iexact=value
        ).values_list("product_id", flat=True)
        
        # Filter by either barcode_scanned or product barcode
        return queryset.filter(
            Q(barcode_scanned__iexact=value) | Q(product_id__in=product_ids)
        )

    def filter_by_provider(self, queryset, name, value):
        """Filter by provider through purchase order."""
        if not value:
            return queryset
        return queryset.filter(purchase_order__provider_id=value)
