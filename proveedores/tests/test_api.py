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
        self.assertIn("amount_boxes", first)
        self.assertIn("units_per_box", first)

    def test_list_providers(self):
        url = "/api/proveedores/providers/"
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(res.data), 1)
        self.assertIn("name", res.data[0])
        self.assertIn("products_count", res.data[0])

    def test_create_and_retrieve_purchase_order(self):
        url = "/api/proveedores/purchase-orders/"
        # Pedido: producto en BOXES
        payload_units = {
            "provider": self.provider.id,
            "ordered_by": self.user.id,
            "status": "PLACED",
            "notes": "Orden unidades",
            "items": [
                {"product": self.product2.id, "quantity_units": 10, "unit_type": "boxes"},
            ],
        }
        res_units = self.client.post(url, data=payload_units, format="json")
        self.assertEqual(res_units.status_code, status.HTTP_201_CREATED)
        po_units_id = res_units.data["id"]
        self.assertEqual(len(res_units.data["items"]), 1)
        self.assertEqual(res_units.data["items"][0]["product"], self.product2.id)
        self.assertEqual(res_units.data["items"][0]["quantity_units"], 10)

        # Retrieve detail de ambos pedidos
        detail_units = self.client.get(f"/api/proveedores/purchase-orders/{po_units_id}/")
        self.assertEqual(detail_units.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_units.data["id"], po_units_id)
        self.assertEqual(detail_units.data["provider"], self.provider.id)
        self.assertEqual(len(detail_units.data["items"]), 1)

    def test_create_purchase_order_sets_and_returns_ordered_by(self):
        url = "/api/proveedores/purchase-orders/"
        # No enviar ordered_by en el payload; debe tomarse del request.user
        payload = {
            "provider": self.provider.id,
            "status": "PLACED",
            "notes": "Orden sin ordered_by en payload",
            "items": [
                {"product": self.product1.id, "quantity_units": 1, "unit_type": "boxes"},
            ],
        }
        res = self.client.post(url, data=payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data.get("ordered_by"), self.user.id)
        self.assertEqual(res.data.get("ordered_by_username"), self.user.username)

    def test_purchase_order_item_persists_purchase_unit(self):
        url = "/api/proveedores/purchase-orders/"
        payload = {
            "provider": self.provider.id,
            "status": "PLACED",
            "notes": "Orden con purchase_unit boxes",
            "items": [
                {"product": self.product2.id, "quantity_units": 5, "purchase_unit": "boxes"},
                {"product": self.product1.id, "quantity_units": 2, "purchase_unit": "boxes"},
            ],
        }
        res = self.client.post(url, data=payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        items = res.data.get("items", [])
        self.assertEqual(len(items), 2)
        # Mapear purchase_unit por producto
        pu_by_product = {it["product"]: it.get("purchase_unit") for it in items}
        self.assertEqual(pu_by_product.get(self.product2.id), "boxes")
        self.assertEqual(pu_by_product.get(self.product1.id), "boxes")

    def test_same_product_multiple_boxes_consolidate(self):
        url = "/api/proveedores/purchase-orders/"
        payload = {
            "provider": self.provider.id,
            "status": "PLACED",
            "notes": "Mismo producto con dos líneas en boxes",
            "items": [
                {"product": self.product2.id, "quantity_units": 4, "purchase_unit": "boxes"},
                {"product": self.product2.id, "quantity_units": 1, "purchase_unit": "boxes"},
            ],
        }
        res = self.client.post(url, data=payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        items = res.data.get("items", [])
        # Debe consolidar en un solo renglón para el mismo producto y purchase_unit
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["product"], self.product2.id)
        self.assertEqual(items[0]["purchase_unit"], "boxes")
        self.assertEqual(items[0]["quantity_units"], 5)

    def test_create_order_same_product_multiple_lines_consolidates(self):
        url = "/api/proveedores/purchase-orders/"
        payload = {
            "provider": self.provider.id,
            "ordered_by": self.user.id,
            "status": "PLACED",
            "notes": "Varias líneas del mismo producto (boxes)",
            "items": [
                {"product": self.product2.id, "quantity_units": 10, "unit_type": "boxes"},
                {"product": self.product2.id, "quantity_units": 2, "unit_type": "boxes"},
            ],
        }
        res = self.client.post(url, data=payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        # Debe consolidar en un solo ítem
        self.assertEqual(len(res.data.get("items", [])), 1)
        item = res.data["items"][0]
        self.assertEqual(item["product"], self.product2.id)
        # Total esperado: 10 boxes + 2 boxes = 12
        self.assertEqual(item["quantity_units"], 12)

    def test_update_purchase_order(self):
        # Crear orden inicial
        create_url = "/api/proveedores/purchase-orders/"
        create_payload = {
            "provider": self.provider.id,
            "ordered_by": self.user.id,
            "status": "PLACED",
            "notes": "Orden inicial",
            "items": [
                {"product": self.product1.id, "quantity_units": 2, "unit_type": "boxes"},
                {"product": self.product2.id, "quantity_units": 1, "unit_type": "boxes"},
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
                {"product": self.product2.id, "quantity_units": 2, "unit_type": "units"},
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
        self.assertEqual(qty_by_product.get(self.product2.id), 2)

    def test_product_last_purchase_amounts_on_create(self):
        url = "/api/proveedores/purchase-orders/"
        payload = {
            "provider": self.provider.id,
            "ordered_by": self.user.id,
            "status": "PLACED",
            "notes": "PO para historial",
            "items": [
                {"product": self.product2.id, "quantity_units": 36, "unit_type": "boxes"},
            ],
        }
        res = self.client.post(url, data=payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        # Consultar detalle del producto y verificar amount_boxes
        prod_detail = self.client.get(f"/api/proveedores/products/{self.product2.id}/")
        self.assertEqual(prod_detail.status_code, status.HTTP_200_OK)
        self.assertEqual(prod_detail.data.get("amount_boxes"), 36)

    def test_product_last_purchase_amounts_on_update(self):
        # Crear orden inicial con unidades
        create_url = "/api/proveedores/purchase-orders/"
        payload = {
            "provider": self.provider.id,
            "ordered_by": self.user.id,
            "status": "PLACED",
            "items": [
                {"product": self.product2.id, "quantity_units": 5, "unit_type": "boxes"},
            ],
        }
        res_create = self.client.post(create_url, data=payload, format="json")
        self.assertEqual(res_create.status_code, status.HTTP_201_CREATED)
        po_id = res_create.data["id"]

        # Verificar referencia inicial (amount_boxes)
        prod_detail_1 = self.client.get(f"/api/proveedores/products/{self.product2.id}/")
        self.assertEqual(prod_detail_1.status_code, status.HTTP_200_OK)
        self.assertEqual(prod_detail_1.data.get("amount_boxes"), 5)

        # Actualizar orden: cambiar a 2 boxes
        patch_url = f"/api/proveedores/purchase-orders/{po_id}/"
        patch_payload = {
            "items": [
                {"product": self.product2.id, "quantity_units": 2, "unit_type": "boxes"},
            ]
        }
        res_patch = self.client.patch(patch_url, data=patch_payload, format="json")
        self.assertIn(res_patch.status_code, (status.HTTP_200_OK, status.HTTP_202_ACCEPTED))

        # Verificar referencia actualizada (amount_boxes)
        prod_detail_2 = self.client.get(f"/api/proveedores/products/{self.product2.id}/")
        self.assertEqual(prod_detail_2.status_code, status.HTTP_200_OK)
        self.assertEqual(prod_detail_2.data.get("amount_boxes"), 2)

    def test_list_purchase_order_items(self):
        # Create a PO to have items
        po = PurchaseOrder.objects.create(provider=self.provider, ordered_by=self.user, status="PLACED")
        PurchaseOrderItem.objects.create(order=po, product=self.product1, quantity_units=3)
        PurchaseOrderItem.objects.create(order=po, product=self.product2, quantity_units=2)

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

    def test_purchase_order_item_includes_product_image(self):
        # Asociar imagen al producto1
        gif_bytes = (
            b"GIF89a"
            b"\x01\x00\x01\x00"
            b"\x80\x00\x00"
            b"\x00\x00\x00"
            b"\x2C\x00\x00\x00\x00\x01\x01\x00\x00"
            b"\x02\x02\x44\x01\x00"
            b"\x3B"
        )
        upload = SimpleUploadedFile("pixel.gif", gif_bytes, content_type="image/gif")
        self.product1.image.save("pixel.gif", upload, save=True)

        # Crear una orden con un ítem de product1
        url = "/api/proveedores/purchase-orders/"
        payload = {
            "provider": self.provider.id,
            "status": "PLACED",
            "items": [
                {"product": self.product1.id, "quantity_units": 2, "unit_type": "boxes"},
            ],
        }
        res_create = self.client.post(url, data=payload, format="json")
        self.assertEqual(res_create.status_code, status.HTTP_201_CREATED)
        self.assertGreaterEqual(len(res_create.data.get("items", [])), 1)
        item = res_create.data["items"][0]
        img_url = item.get("product_image")
        self.assertIsNotNone(img_url)
        self.assertTrue(img_url.startswith("https://"))

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

    def test_has_ordered_today_with_provider_filter(self):
        base_url = "/api/proveedores/purchase-orders/has-ordered-today/"
        # Crear otra proveedor
        other_provider = Provider.objects.create(name="Proveedor B")
        # Crear una orden hoy con provider principal
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

        # Filtro por provider correcto -> true
        res_yes = self.client.get(f"{base_url}?provider={self.provider.id}")
        self.assertEqual(res_yes.status_code, status.HTTP_200_OK)
        self.assertTrue(res_yes.data.get("has_ordered_today"))

        # Filtro por provider distinto -> false
        res_no = self.client.get(f"{base_url}?provider={other_provider.id}")
        self.assertEqual(res_no.status_code, status.HTTP_200_OK)
        self.assertFalse(res_no.data.get("has_ordered_today"))

    def test_has_ordered_today_with_invalid_provider_param(self):
        url = "/api/proveedores/purchase-orders/has-ordered-today/?provider=abc"
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", res.data)

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
    
    def test_purchase_order_queryset_for_by_day_and_provider(self):
        from django.utils import timezone
        from datetime import timedelta

        # Crear otro proveedor
        other_provider = Provider.objects.create(name="Proveedor C")

        # Crear dos órdenes hoy: una para provider principal (más antigua) y otra para el otro provider (más reciente)
        po1 = PurchaseOrder.objects.create(provider=self.provider, ordered_by=self.user, status="PLACED")
        po2 = PurchaseOrder.objects.create(provider=other_provider, ordered_by=self.user, status="PLACED")

        # Ajustar created_at para que po1 sea más antigua que po2
        older = timezone.now() - timedelta(hours=1)
        PurchaseOrder.objects.filter(id=po1.id).update(created_at=older)

        day = timezone.now().date().isoformat()

        # Filtro por provider principal -> debe devolver po1
        res_main = self.client.get(f"/api/proveedores/purchase-orders/by-day/?date={day}&provider={self.provider.id}")
        self.assertEqual(res_main.status_code, status.HTTP_200_OK)
        self.assertIsInstance(res_main.data, dict)
        self.assertEqual(res_main.data.get("provider"), self.provider.id)

        # Filtro por otro provider -> debe devolver po2 (la más reciente de ese provider)
        res_other = self.client.get(f"/api/proveedores/purchase-orders/by-day/?date={day}&provider={other_provider.id}")
        self.assertEqual(res_other.status_code, status.HTTP_200_OK)
        self.assertIsInstance(res_other.data, dict)
        self.assertEqual(res_other.data.get("provider"), other_provider.id)

        # provider inválido -> 400
        res_bad = self.client.get(f"/api/proveedores/purchase-orders/by-day/?date={day}&provider=abc")
        self.assertEqual(res_bad.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", res_bad.data)
