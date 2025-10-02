"""Tests para el modelo Product y su API."""

import pytest
from urllib.parse import urlparse
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status

from proveedores.models import Product, ProductFavorite


def test_list_products(auth_client, product1, product2):
    """Verifica que se pueda listar productos."""
    url = "/api/products/"
    res = auth_client.get(url)
    assert res.status_code == status.HTTP_200_OK
    # Should list at least the two products
    assert len(res.data) >= 2
    first = res.data[0]
    assert "name" in first
    assert "sku" in first
    assert "providers" in first
    assert "amount_boxes" in first
    assert "units_per_box" in first


def test_favorite_product(auth_client, user, product1):
    """Verifica que se pueda marcar un producto como favorito."""
    # Marcar como favorito
    fav_url = f"/api/products/{product1.id}/favorite/"
    res = auth_client.post(fav_url)
    assert res.status_code == status.HTTP_201_CREATED
    assert ProductFavorite.objects.filter(user=user, product=product1).exists()

    # Recuperar detalle del producto y verificar flags de favorito
    detail_url = f"/api/products/{product1.id}/"
    res2 = auth_client.get(detail_url)
    assert res2.status_code == status.HTTP_200_OK
    assert res2.data.get("current_user_favorite")


def test_unfavorite_product(auth_client, user, product1):
    """Verifica que se pueda quitar un producto de favoritos."""
    # Precondición: producto ya favorito
    ProductFavorite.objects.create(user=user, product=product1)

    unfav_url = f"/api/products/{product1.id}/unfavorite/"
    res = auth_client.post(unfav_url)
    assert res.status_code == status.HTTP_200_OK
    assert not ProductFavorite.objects.filter(user=user, product=product1).exists()

    # Recuperar detalle del producto y verificar flags de favorito
    detail_url = f"/api/products/{product1.id}/"
    res2 = auth_client.get(detail_url)
    assert res2.status_code == status.HTTP_200_OK
    assert not res2.data.get("current_user_favorite")


def test_my_favorites_list(auth_client, product1, product2):
    """Verifica que se pueda obtener la lista de productos favoritos del usuario."""
    # Marcar product1 como favorito; product2 no
    fav_url = f"/api/products/{product1.id}/favorite/"
    res = auth_client.post(fav_url)
    assert res.status_code == status.HTTP_201_CREATED

    # Obtener lista de mis favoritos
    url = "/api/products/my-favorites/"
    res_list = auth_client.get(url)
    assert res_list.status_code == status.HTTP_200_OK

    data = res_list.data
    assert len(data) >= 1
    ids = {item.get("id") for item in data}
    assert product1.id in ids
    assert product2.id not in ids


def test_product_image_absolute_https_url(auth_client, product1, product2):
    """Verifica que la imagen del producto se devuelva como URL absoluta HTTPS."""
    # Crear y asociar una imagen mínima (GIF de 1x1) al producto1
    gif_bytes = (
        b"GIF89a"  # header
        b"\x01\x00\x01\x00"  # width=1, height=1
        b"\x80\x00\x00"  # GCT follows for 1 color
        b"\x00\x00\x00"  # black
        b"\x2C\x00\x00\x00\x00\x01\x01\x00\x00"  # image descriptor
        b"\x02\x02\x44\x01\x00"  # image data
        b"\x3B"  # trailer
    )
    upload = SimpleUploadedFile("pixel.gif", gif_bytes, content_type="image/gif")
    product1.image.save("pixel.gif", upload, save=True)

    # Detalle del producto para ver el serializer
    detail_url = f"/api/products/{product1.id}/"
    res = auth_client.get(detail_url)
    assert res.status_code == status.HTTP_200_OK
    img_url = res.data.get("image")
    assert img_url is not None
    # Debe ser absoluta y https; y apuntar al path de products
    assert img_url.startswith("https://")
    parsed = urlparse(img_url)
    assert parsed.netloc
    assert parsed.path.startswith("/products/")
    assert parsed.path.endswith(".gif")

    # Para producto sin imagen debe venir null
    detail_url2 = f"/api/products/{product2.id}/"
    res2 = auth_client.get(detail_url2)
    assert res2.status_code == status.HTTP_200_OK
    assert res2.data.get("image") is None


def test_products_ordering_parameter(auth_client):
    """Test que verifica el parámetro ordering en el endpoint de productos."""
    # Crear productos adicionales para probar ordenamiento
    Product.objects.create(name="Zebra Product", sku="SKU-Z")
    Product.objects.create(name="Alpha Product", sku="SKU-A")
    
    # Test 1: Ordenamiento ascendente por nombre (por defecto)
    url = "/api/products/"
    res = auth_client.get(url)
    assert res.status_code == status.HTTP_200_OK
    names = [product["name"] for product in res.data]
    assert names == sorted(names)  # Debe estar ordenado ascendente
    
    # Test 2: Ordenamiento ascendente explícito
    url = "/api/products/?ordering=name"
    res = auth_client.get(url)
    assert res.status_code == status.HTTP_200_OK
    names = [product["name"] for product in res.data]
    assert names == sorted(names)  # Debe estar ordenado ascendente
    
    # Test 3: Ordenamiento descendente por nombre
    url = "/api/products/?ordering=-name"
    res = auth_client.get(url)
    assert res.status_code == status.HTTP_200_OK
    names = [product["name"] for product in res.data]
    assert names == sorted(names, reverse=True)  # Debe estar ordenado descendente
