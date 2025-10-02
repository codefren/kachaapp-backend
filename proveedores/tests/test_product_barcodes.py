"""Tests para ProductBarcode y filtros por código de barras."""

import pytest
from rest_framework import status

from proveedores.models import ProductBarcode


def test_filter_products_by_barcode(auth_client, product1):
    """Verifica que se puedan filtrar productos por código de barras."""
    # Crear barcode para product1
    bc1 = ProductBarcode.objects.create(
        product=product1, 
        code="CODE-111", 
        type=ProductBarcode.BarcodeType.EAN13
    )

    # Filtrar por barcode de product1
    url = f"/api/products/?barcode={bc1.code}"
    res = auth_client.get(url)
    assert res.status_code == status.HTTP_200_OK
    data = res.data if isinstance(res.data, list) else res.data.get("results", [])
    assert len(data) == 1
    assert data[0]["id"] == product1.id


def test_filter_products_by_barcode_no_match(auth_client):
    """Verifica que filtrar por un código de barras inexistente no devuelva resultados."""
    # Sin barcodes o con código inexistente
    url = "/api/products/?barcode=NOT-EXISTS"
    res = auth_client.get(url)
    assert res.status_code == status.HTTP_200_OK
    data = res.data if isinstance(res.data, list) else res.data.get("results", [])
    assert len(data) == 0
