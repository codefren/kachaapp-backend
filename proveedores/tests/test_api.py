from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from urllib.parse import urlparse
from rest_framework.test import APITestCase
from rest_framework import status

from proveedores.models import Provider, Product, PurchaseOrder, PurchaseOrderItem, ProductFavorite, ProductBarcode


class ProveedoresAPITests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="tester", password="pass1234")
        # Autenticar todas las peticiones del cliente de prueba
        self.client.force_authenticate(user=self.user)
        self.provider = Provider.objects.create(name="Proveedor A")
        self.product1 = Product.objects.create(name="Producto 1", sku="SKU-1")
        self.product1.providers.add(self.provider)
        self.product2 = Product.objects.create(name="Producto 2", sku="SKU-2")
        self.product2.providers.add(self.provider)

    def test_root(self):
        url = "/api/proveedores/"
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("message", res.data)

    def test_list_products(self):
        url = "/api/proveedores/products/"
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        # Should list at least the two products
        self.assertGreaterEqual(len(res.data), 2)
        first = res.data[0]
        self.assertIn("name", first)
        self.assertIn("sku", first)
        self.assertIn("providers", first)

    def test_list_providers(self):
        url = "/api/proveedores/providers/"
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(res.data), 1)
        self.assertIn("name", res.data[0])
        self.assertIn("products_count", res.data[0])

    def test_create_and_retrieve_purchase_order(self):
        url = "/api/proveedores/purchase-orders/"
        payload = {
            "provider": self.provider.id,
            "ordered_by": self.user.id,
            "status": "PLACED",
            "notes": "Orden de prueba",
            "items": [
                {"product": self.product1.id, "quantity_units": 10, "unit_type": "units"},
                {"product": self.product2.id, "quantity_units": 5, "unit_type": "boxes"},
            ],
        }
        res = self.client.post(url, data=payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        po_id = res.data["id"]
        self.assertEqual(len(res.data["items"]), 2)

        # Retrieve detail
        detail_url = f"/api/proveedores/purchase-orders/{po_id}/"
        res2 = self.client.get(detail_url)
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        self.assertEqual(res2.data["id"], po_id)
        self.assertEqual(res2.data["provider"], self.provider.id)
        self.assertEqual(len(res2.data["items"]), 2)

    def test_update_purchase_order(self):
        # Asegurar que boxes convierta correctamente: 1 caja = 12 unidades para product2
        self.product2.units_per_box = 12
        self.product2.save()

        # Crear orden inicial
        create_url = "/api/proveedores/purchase-orders/"
        create_payload = {
            "provider": self.provider.id,
            "ordered_by": self.user.id,
            "status": "PLACED",
            "notes": "Orden inicial",
            "items": [
                {"product": self.product1.id, "quantity_units": 2, "unit_type": "units"},
                {"product": self.product2.id, "quantity_units": 1, "unit_type": "units"},
            ],
        }
        res_create = self.client.post(create_url, data=create_payload, format="json")
        self.assertEqual(res_create.status_code, status.HTTP_201_CREATED)
        po_id = res_create.data["id"]

        # Actualizar: cambiar notas e ítems (uno en unidades, otro en cajas)
        detail_url = f"/api/proveedores/purchase-orders/{po_id}/"
        patch_payload = {
            "notes": "Orden actualizada",
            "items": [
                {"product": self.product1.id, "quantity_units": 4, "unit_type": "units"},
                {"product": self.product2.id, "quantity_units": 2, "unit_type": "boxes"},  # 2 cajas -> 24 unidades
            ],
        }
        res_patch = self.client.patch(detail_url, data=patch_payload, format="json")
        self.assertIn(res_patch.status_code, (status.HTTP_200_OK, status.HTTP_202_ACCEPTED))

        # Verificar detalle
        res_detail = self.client.get(detail_url)
        self.assertEqual(res_detail.status_code, status.HTTP_200_OK)
        self.assertEqual(res_detail.data.get("notes"), "Orden actualizada")
        self.assertEqual(len(res_detail.data.get("items", [])), 2)

        # Mapear cantidades por producto
        items = res_detail.data["items"]
        qty_by_product = {it["product"]: it["quantity_units"] for it in items}
        self.assertEqual(qty_by_product.get(self.product1.id), 4)
        self.assertEqual(qty_by_product.get(self.product2.id), 24)  # 2 cajas * 12

    def test_list_purchase_order_items(self):
        # Create a PO to have items
        po = PurchaseOrder.objects.create(provider=self.provider, ordered_by=self.user, status="PLACED")
        PurchaseOrderItem.objects.create(order=po, product=self.product1, quantity_units=3, unit_price=1.25)
        PurchaseOrderItem.objects.create(order=po, product=self.product2, quantity_units=2, unit_price=2.50)

        url = "/api/proveedores/purchase-order-items/"
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(res.data), 2)
        self.assertIn("product", res.data[0])
        self.assertIn("quantity_units", res.data[0])

    def test_favorite_product(self):
        # Marcar como favorito
        fav_url = f"/api/proveedores/products/{self.product1.id}/favorite/"
        res = self.client.post(fav_url)
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            ProductFavorite.objects.filter(user=self.user, product=self.product1).exists()
        )

        # Recuperar detalle del producto y verificar flags de favorito
        detail_url = f"/api/proveedores/products/{self.product1.id}/"
        res2 = self.client.get(detail_url)
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        self.assertTrue(res2.data.get("current_user_favorite"))
        # favorites_count eliminado del serializer

    def test_unfavorite_product(self):
        # Precondición: producto ya favorito
        ProductFavorite.objects.create(user=self.user, product=self.product1)

        unfav_url = f"/api/proveedores/products/{self.product1.id}/unfavorite/"
        res = self.client.post(unfav_url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertFalse(
            ProductFavorite.objects.filter(user=self.user, product=self.product1).exists()
        )

        # Recuperar detalle del producto y verificar flags de favorito
        detail_url = f"/api/proveedores/products/{self.product1.id}/"
        res2 = self.client.get(detail_url)
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        self.assertFalse(res2.data.get("current_user_favorite"))
        # favorites_count eliminado del serializer

    def test_my_favorites_list(self):
        # Marcar product1 como favorito; product2 no
        fav_url = f"/api/proveedores/products/{self.product1.id}/favorite/"
        res = self.client.post(fav_url)
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        # Obtener lista de mis favoritos
        url = "/api/proveedores/products/my-favorites/"
        res_list = self.client.get(url)
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)

        data = res_list.data
        self.assertGreaterEqual(len(data), 1)
        ids = {item.get("id") for item in data}
        self.assertIn(self.product1.id, ids)
        self.assertNotIn(self.product2.id, ids)

    def test_product_image_absolute_https_url(self):
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
        self.product1.image.save("pixel.gif", upload, save=True)

        # Detalle del producto para ver el serializer
        detail_url = f"/api/proveedores/products/{self.product1.id}/"
        res = self.client.get(detail_url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        img_url = res.data.get("image")
        self.assertIsNotNone(img_url)
        # Debe ser absoluta y https; y apuntar al path de products
        self.assertTrue(img_url.startswith("https://"))
        parsed = urlparse(img_url)
        self.assertTrue(parsed.netloc)
        self.assertTrue(parsed.path.startswith("/products/"))
        self.assertTrue(parsed.path.endswith(".gif"))

        # Para producto sin imagen debe venir null
        detail_url2 = f"/api/proveedores/products/{self.product2.id}/"
        res2 = self.client.get(detail_url2)
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        self.assertIsNone(res2.data.get("image"))

    def test_filter_products_by_barcode(self):
        # Crear barcodes para ambos productos
        bc1 = ProductBarcode.objects.create(product=self.product1, code="CODE-111", type=ProductBarcode.BarcodeType.EAN13)

        # Filtrar por barcode de product1
        url = f"/api/proveedores/products/?barcode={bc1.code}"
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.data if isinstance(res.data, list) else res.data.get("results", [])
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["id"], self.product1.id)

    def test_filter_products_by_barcode_no_match(self):
        # Sin barcodes o con código inexistente
        url = "/api/proveedores/products/?barcode=NOT-EXISTS"
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.data if isinstance(res.data, list) else res.data.get("results", [])
        self.assertEqual(len(data), 0)

    def test_has_ordered_today(self):
        url = "/api/proveedores/purchase-orders/has-ordered-today/"
        # Inicialmente, no debe haber órdenes hoy
        res1 = self.client.get(url)
        self.assertEqual(res1.status_code, status.HTTP_200_OK)
        self.assertFalse(res1.data.get("has_ordered_today"))

        # Crear una orden hoy
        create_url = "/api/proveedores/purchase-orders/"
        payload = {
            "provider": self.provider.id,
            "ordered_by": self.user.id,
            "status": "PLACED",
            "items": [
                {"product": self.product1.id, "quantity_units": 1, "unit_type": "units"},
            ],
        }
        res_create = self.client.post(create_url, data=payload, format="json")
        self.assertEqual(res_create.status_code, status.HTTP_201_CREATED)

        # Ahora debe retornar true
        res2 = self.client.get(url)
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        self.assertTrue(res2.data.get("has_ordered_today"))

    def test_filter_purchase_orders_by_date(self):
        # Crear 2 órdenes
        url = "/api/proveedores/purchase-orders/"
        payload1 = {
            "provider": self.provider.id,
            "ordered_by": self.user.id,
            "status": "PLACED",
            "items": [
                {"product": self.product1.id, "quantity_units": 1, "unit_type": "units"},
            ],
        }
        res1 = self.client.post(url, data=payload1, format="json")
        self.assertEqual(res1.status_code, status.HTTP_201_CREATED)

        payload2 = {
            "provider": self.provider.id,
            "ordered_by": self.user.id,
            "status": "PLACED",
            "items": [
                {"product": self.product2.id, "quantity_units": 1, "unit_type": "units"},
            ],
        }
        res2 = self.client.post(url, data=payload2, format="json")
        self.assertEqual(res2.status_code, status.HTTP_201_CREATED)

        # Mover la segunda orden a "ayer" modificando created_at
        from django.utils import timezone
        from datetime import timedelta
        po2_id = res2.data["id"]
        yesterday = timezone.now() - timedelta(days=1)
        PurchaseOrder.objects.filter(id=po2_id).update(created_at=yesterday)

        # Consultar por hoy con la acción by-day: debe devolver un objeto (la orden de hoy)
        today_str = timezone.now().date().isoformat()
        res_today = self.client.get(f"/api/proveedores/purchase-orders/by-day/?date={today_str}")
        self.assertEqual(res_today.status_code, status.HTTP_200_OK)
        self.assertIsInstance(res_today.data, dict)

        # Consultar por ayer con la acción by-day: debe devolver un objeto (la orden movida a ayer)
        yesterday_str = (timezone.now() - timedelta(days=1)).date().isoformat()
        res_yest = self.client.get(f"/api/proveedores/purchase-orders/by-day/?date={yesterday_str}")
        self.assertEqual(res_yest.status_code, status.HTTP_200_OK)
        self.assertIsInstance(res_yest.data, dict)

    def test_purchase_order_queryset_no_date_returns_all(self):
        # Crear 2 órdenes hoy
        url = "/api/proveedores/purchase-orders/"
        for _ in range(2):
            payload = {
                "provider": self.provider.id,
                "ordered_by": self.user.id,
                "status": "PLACED",
                "items": [
                    {"product": self.product1.id, "quantity_units": 1, "unit_type": "units"},
                ],
            }
            res = self.client.post(url, data=payload, format="json")
            self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        # Sin parámetro date debe devolver todas
        res_list = self.client.get(url)
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        data = res_list.data if isinstance(res_list.data, list) else res_list.data.get("results", [])
        self.assertEqual(len(data), 2)

    # --- Tests para la acción by-day ---
    def test_by_day_no_results_returns_message(self):
        from django.utils import timezone
        from datetime import timedelta
        future_day = (timezone.now() + timedelta(days=15)).date().isoformat()
        res = self.client.get(f"/api/proveedores/purchase-orders/by-day/?date={future_day}")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIsInstance(res.data, dict)
        self.assertEqual(res.data.get("detail"), "No existen órdenes para el día seleccionado.")

    def test_by_day_missing_date_returns_400(self):
        res = self.client.get("/api/proveedores/purchase-orders/by-day/")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", res.data)

    def test_by_day_invalid_date_returns_400(self):
        res = self.client.get("/api/proveedores/purchase-orders/by-day/?date=2025-13-40")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", res.data)

    def test_by_day_with_result_returns_single_object(self):
        # Crear una orden hoy
        url = "/api/proveedores/purchase-orders/"
        payload = {
            "provider": self.provider.id,
            "ordered_by": self.user.id,
            "status": "PLACED",
            "items": [
                {"product": self.product1.id, "quantity_units": 2, "unit_type": "units"},
            ],
        }
        res_create = self.client.post(url, data=payload, format="json")
        self.assertEqual(res_create.status_code, status.HTTP_201_CREATED)

        from django.utils import timezone
        day = timezone.now().date().isoformat()
        res = self.client.get(f"/api/proveedores/purchase-orders/by-day/?date={day}")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        # Debe ser un objeto, no lista
        self.assertIsInstance(res.data, dict)
        self.assertIn("id", res.data)

    def test_list_purchase_orders_with_date_no_results_returns_message(self):
        # Asegurarnos de que no haya órdenes en una fecha futura
        from django.utils import timezone
        from datetime import timedelta
        future_day = (timezone.now() + timedelta(days=30)).date().isoformat()

        url = f"/api/proveedores/purchase-orders/by-day/?date={future_day}"
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        # Debe devolver un objeto con 'detail' y no una lista vacía
        self.assertIsInstance(res.data, dict)
        self.assertIn("detail", res.data)
        self.assertEqual(res.data["detail"], "No existen órdenes para el día seleccionado.")

    def test_purchase_order_queryset_invalid_date_returns_all(self):
        # Crear 2 órdenes hoy
        url = "/api/proveedores/purchase-orders/"
        for _ in range(2):
            payload = {
                "provider": self.provider.id,
                "ordered_by": self.user.id,
                "status": "PLACED",
                "items": [
                    {"product": self.product2.id, "quantity_units": 1, "unit_type": "units"},
                ],
            }
            res = self.client.post(url, data=payload, format="json")
            self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        # date inválido debe ignorarse y devolver todas
        res_list = self.client.get(f"{url}?date=2025-13-40")
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        data = res_list.data if isinstance(res_list.data, list) else res_list.data.get("results", [])
        self.assertEqual(len(data), 2)
