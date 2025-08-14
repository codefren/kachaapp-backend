from rest_framework.decorators import api_view
from rest_framework.response import Response


from django.conf import settings
from ftplib import FTP
import io
import json
from .models import Product, Provider

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
def proveedores_root(request):
    """Simple root endpoint for proveedores module."""
    return Response({"message": "Proveedores API root"})
