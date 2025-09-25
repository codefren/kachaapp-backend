from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from urllib.parse import urlparse
from rest_framework.test import APITestCase
from rest_framework import status

from proveedores.models import Provider, Product, PurchaseOrder, PurchaseOrderItem, ProductFavorite, ProductBarcode


class ProveedoresAPITests(APITestCase):
    def setUp(self):
        from datetime import time

        User = get_user_model()
        self.user = User.objects.create_user(username="tester", password="pass1234")
        # Autenticar todas las peticiones del cliente de prueba
        self.client.force_authenticate(user=self.user)
        self.provider = Provider.objects.create(
            name="Proveedor A",
            order_deadline_time=time(14, 30),
            order_available_weekdays=[0, 1, 2, 3, 4]  # Lun-Vie
        )
        self.product1 = Product.objects.create(name="Producto 1", sku="SKU-1")
        self.product1.providers.add(self.provider)
        self.product2 = Product.objects.create(name="Producto 2", sku="SKU-2")
        self.product2.providers.add(self.provider)

    def test_root(self):
        url = "/api/"
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("message", res.data)

    def test_list_products(self):
        url = "/api/products/"
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
        url = "/api/providers/"
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(res.data), 1)
        self.assertIn("name", res.data[0])
        self.assertIn("products_count", res.data[0])

    def test_create_and_retrieve_purchase_order(self):
        url = "/api/purchase-orders/"
        # Pedido: producto en BOXES
        payload_units = {
            "provider": self.provider.id,
            "ordered_by": self.user.id,
            "status": "PLACED",
            "notes": "Orden unidades",
            "items": [
                {"product": self.product2.id, "quantity_units": 10, "unit_type": "boxes", "amount_boxes": 10},
            ],
        }
        res_units = self.client.post(url, data=payload_units, format="json")
        self.assertEqual(res_units.status_code, status.HTTP_201_CREATED)
        po_units_id = res_units.data["id"]
        self.assertEqual(len(res_units.data["items"]), 1)
        self.assertEqual(res_units.data["items"][0]["product"], self.product2.id)
        self.assertEqual(res_units.data["items"][0]["quantity_units"], 10)

        # Retrieve detail de ambos pedidos
        detail_units = self.client.get(f"/api/purchase-orders/{po_units_id}/")
        self.assertEqual(detail_units.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_units.data["id"], po_units_id)
        self.assertEqual(detail_units.data["provider"], self.provider.id)
        self.assertEqual(len(detail_units.data["items"]), 1)

    def test_create_purchase_order_sets_and_returns_ordered_by(self):
        url = "/api/purchase-orders/"
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
        url = "/api/purchase-orders/"
        payload = {
            "provider": self.provider.id,
            "status": "PLACED",
            "notes": "Orden con purchase_unit boxes",
            "items": [
                {"product": self.product2.id, "quantity_units": 5, "purchase_unit": "boxes", "amount_boxes": 5},
                {"product": self.product1.id, "quantity_units": 2, "purchase_unit": "boxes", "amount_boxes": 2},
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

    def test_same_product_multiple_boxes_consolidates(self):
        url = "/api/purchase-orders/"
        payload = {
            "provider": self.provider.id,
            "status": "PLACED",
            "notes": "Mismo producto con dos líneas en boxes",
            "items": [
                {"product": self.product2.id, "quantity_units": 4, "purchase_unit": "boxes", "amount_boxes": 4},
                {"product": self.product2.id, "quantity_units": 1, "purchase_unit": "boxes", "amount_boxes": 1},
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
        url = "/api/purchase-orders/"
        payload = {
            "provider": self.provider.id,
            "ordered_by": self.user.id,
            "status": "PLACED",
            "notes": "Varias líneas del mismo producto (boxes)",
            "items": [
                {"product": self.product2.id, "quantity_units": 10, "unit_type": "boxes", "amount_boxes": 10},
                {"product": self.product2.id, "quantity_units": 2, "unit_type": "boxes", "amount_boxes": 2},
            ],
        }
        res = self.client.post(url, data=payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        # Debe consolidar en un solo ítem con la suma de cantidades
        self.assertEqual(len(res.data.get("items", [])), 1)
        item = res.data["items"][0]
        self.assertEqual(item["product"], self.product2.id)
        self.assertEqual(item["quantity_units"], 12)

    def test_update_purchase_order(self):
        # Crear orden inicial
        create_url = "/api/purchase-orders/"
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
        detail_url = f"/api/purchase-orders/{po_id}/"
        patch_payload = {
            "notes": "Orden actualizada",
            "items": [
                {"product": self.product1.id, "quantity_units": 4, "unit_type": "boxes", "amount_boxes": 4},
                {"product": self.product2.id, "quantity_units": 2, "unit_type": "boxes", "amount_boxes": 2},
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
        url = "/api/purchase-orders/"
        payload = {
            "provider": self.provider.id,
            "ordered_by": self.user.id,
            "status": "PLACED",
            "notes": "PO para historial",
            "items": [
                {"product": self.product2.id, "quantity_units": 36, "unit_type": "boxes", "amount_boxes": 36},
            ],
        }
        res = self.client.post(url, data=payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)


    def test_product_last_purchase_amounts_on_update(self):
        # Crear orden inicial con unidades
        create_url = "/api/purchase-orders/"
        payload = {
            "provider": self.provider.id,
            "ordered_by": self.user.id,
            "status": "PLACED",
            "items": [
                {"product": self.product2.id, "quantity_units": 5, "unit_type": "boxes", "amount_boxes": 5},
            ],
        }
        res_create = self.client.post(create_url, data=payload, format="json")
        self.assertEqual(res_create.status_code, status.HTTP_201_CREATED)
        po_id = res_create.data["id"]

        # Actualizar orden: cambiar a 2 boxes
        patch_url = f"/api/purchase-orders/{po_id}/"
        patch_payload = {
            "items": [
                {"product": self.product2.id, "quantity_units": 2, "unit_type": "boxes", "amount_boxes": 2},
            ]
        }
        res_patch = self.client.patch(patch_url, data=patch_payload, format="json")
        self.assertIn(res_patch.status_code, (status.HTTP_200_OK, status.HTTP_202_ACCEPTED))

        # Verificar referencia actualizada (amount_boxes)
        prod_detail_2 = self.client.get(f"/api/products/{self.product2.id}/")
        self.assertEqual(prod_detail_2.status_code, status.HTTP_200_OK)
        self.assertEqual(prod_detail_2.data.get("amount_boxes"), 2)

    def test_list_purchase_order_items(self):
        # Create a PO to have items
        po = PurchaseOrder.objects.create(provider=self.provider, ordered_by=self.user, status="PLACED")
        PurchaseOrderItem.objects.create(order=po, product=self.product1, quantity_units=3)
        PurchaseOrderItem.objects.create(order=po, product=self.product2, quantity_units=2)

        url = "/api/purchase-order-items/"
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(res.data), 2)
        self.assertIn("product", res.data[0])
        self.assertIn("quantity_units", res.data[0])

    def test_favorite_product(self):
        # Marcar como favorito
        fav_url = f"/api/products/{self.product1.id}/favorite/"
        res = self.client.post(fav_url)
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            ProductFavorite.objects.filter(user=self.user, product=self.product1).exists()
        )

        # Recuperar detalle del producto y verificar flags de favorito
        detail_url = f"/api/products/{self.product1.id}/"
        res2 = self.client.get(detail_url)
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        self.assertTrue(res2.data.get("current_user_favorite"))
        # favorites_count eliminado del serializer

    def test_unfavorite_product(self):
        # Precondición: producto ya favorito
        ProductFavorite.objects.create(user=self.user, product=self.product1)

        unfav_url = f"/api/products/{self.product1.id}/unfavorite/"
        res = self.client.post(unfav_url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertFalse(
            ProductFavorite.objects.filter(user=self.user, product=self.product1).exists()
        )

        # Recuperar detalle del producto y verificar flags de favorito
        detail_url = f"/api/products/{self.product1.id}/"
        res2 = self.client.get(detail_url)
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        self.assertFalse(res2.data.get("current_user_favorite"))
        # favorites_count eliminado del serializer

    def test_my_favorites_list(self):
        # Marcar product1 como favorito; product2 no
        fav_url = f"/api/products/{self.product1.id}/favorite/"
        res = self.client.post(fav_url)
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        # Obtener lista de mis favoritos
        url = "/api/products/my-favorites/"
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
        detail_url = f"/api/products/{self.product1.id}/"
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
        detail_url2 = f"/api/products/{self.product2.id}/"
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
        url = "/api/purchase-orders/"
        payload = {
            "provider": self.provider.id,
            "status": "PLACED",
            "items": [
                {"product": self.product1.id, "quantity_units": 2, "unit_type": "boxes", "amount_boxes": 2},
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
        url = f"/api/products/?barcode={bc1.code}"
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.data if isinstance(res.data, list) else res.data.get("results", [])
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["id"], self.product1.id)

    def test_filter_products_by_barcode_no_match(self):
        # Sin barcodes o con código inexistente
        url = "/api/products/?barcode=NOT-EXISTS"
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.data if isinstance(res.data, list) else res.data.get("results", [])
        self.assertEqual(len(data), 0)

    def test_has_ordered_today(self):
        url = "/api/purchase-orders/has-ordered-today/"
        # Inicialmente, no debe haber órdenes hoy
        res1 = self.client.get(url)
        self.assertEqual(res1.status_code, status.HTTP_200_OK)
        self.assertFalse(res1.data.get("has_ordered_today"))

        # Crear una orden hoy
        create_url = "/api/purchase-orders/"
        payload = {
            "provider": self.provider.id,
            "ordered_by": self.user.id,
            "status": "PLACED",
            "items": [
                {"product": self.product1.id, "quantity_units": 1, "unit_type": "boxes", "amount_boxes": 1},
            ],
        }
        res_create = self.client.post(create_url, data=payload, format="json")
        self.assertEqual(res_create.status_code, status.HTTP_201_CREATED)

        # Ahora debe retornar true
        res2 = self.client.get(url)
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        self.assertTrue(res2.data.get("has_ordered_today"))

    def test_has_ordered_today_with_provider_filter(self):
        from datetime import time

        base_url = "/api/purchase-orders/has-ordered-today/"
        # Crear otra proveedor
        other_provider = Provider.objects.create(
            name="Proveedor B",
            order_deadline_time=time(16, 0),
            order_available_weekdays=[0, 1, 2, 3, 4]
        )
        # Crear una orden hoy con provider principal
        create_url = "/api/purchase-orders/"
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
        url = "/api/purchase-orders/has-ordered-today/?provider=abc"
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", res.data)

    def test_filter_purchase_orders_by_date(self):
        # Crear 2 órdenes
        url = "/api/purchase-orders/"
        payload1 = {
            "provider": self.provider.id,
            "ordered_by": self.user.id,
            "status": "PLACED",
            "items": [
                {"product": self.product1.id, "quantity_units": 1, "unit_type": "boxes", "amount_boxes": 1},
            ],
        }
        res1 = self.client.post(url, data=payload1, format="json")
        self.assertEqual(res1.status_code, status.HTTP_201_CREATED)

        payload2 = {
            "provider": self.provider.id,
            "ordered_by": self.user.id,
            "status": "PLACED",
            "items": [
                {"product": self.product2.id, "quantity_units": 1, "unit_type": "boxes", "amount_boxes": 1},
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
        res_today = self.client.get(f"/api/purchase-orders/by-day/?date={today_str}")
        self.assertEqual(res_today.status_code, status.HTTP_200_OK)
        self.assertIsInstance(res_today.data, dict)

        # Consultar por ayer con la acción by-day: debe devolver un objeto (la orden movida a ayer)
        yesterday_str = (timezone.now() - timedelta(days=1)).date().isoformat()
        res_yest = self.client.get(f"/api/purchase-orders/by-day/?date={yesterday_str}")
        self.assertEqual(res_yest.status_code, status.HTTP_200_OK)
        self.assertIsInstance(res_yest.data, dict)

    def test_purchase_order_queryset_no_date_returns_all(self):
        # Crear 2 órdenes hoy
        url = "/api/purchase-orders/"
        for _ in range(2):
            payload = {
                "provider": self.provider.id,
                "ordered_by": self.user.id,
                "status": "PLACED",
                "items": [
                    {"product": self.product1.id, "quantity_units": 1, "unit_type": "boxes", "amount_boxes": 1},
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
        res = self.client.get(f"/api/purchase-orders/by-day/?date={future_day}")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIsInstance(res.data, dict)
        self.assertEqual(res.data.get("detail"), "No existen órdenes para el día seleccionado.")

    def test_by_day_missing_date_returns_400(self):
        res = self.client.get("/api/purchase-orders/by-day/")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", res.data)

    def test_by_day_invalid_date_returns_400(self):
        res = self.client.get("/api/purchase-orders/by-day/?date=2025-13-40")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", res.data)

    def test_by_day_with_result_returns_single_object(self):
        # Crear una orden hoy
        url = "/api/purchase-orders/"
        payload = {
            "provider": self.provider.id,
            "ordered_by": self.user.id,
            "status": "PLACED",
            "items": [
                {"product": self.product1.id, "quantity_units": 2, "unit_type": "boxes", "amount_boxes": 2},
            ],
        }
        res_create = self.client.post(url, data=payload, format="json")
        self.assertEqual(res_create.status_code, status.HTTP_201_CREATED)

        from django.utils import timezone
        day = timezone.now().date().isoformat()
        res = self.client.get(f"/api/purchase-orders/by-day/?date={day}")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        # Debe ser un objeto, no lista
        self.assertIsInstance(res.data, dict)
        self.assertIn("id", res.data)

    def test_purchase_order_create_update_includes_amount_boxes_in_items(self):
        # Crear una orden con un ítem y validar que en la respuesta venga amount_boxes en items
        create_url = "/api/purchase-orders/"
        payload_create = {
            "provider": self.provider.id,
            "status": "PLACED",
            "items": [
                {"product": self.product2.id, "quantity_units": 7, "unit_type": "boxes", "amount_boxes": 7},
            ],
        }
        res_create = self.client.post(create_url, data=payload_create, format="json")
        self.assertEqual(res_create.status_code, status.HTTP_201_CREATED)
        self.assertGreaterEqual(len(res_create.data.get("items", [])), 1)
        item_create = res_create.data["items"][0]
        # amount_boxes debe estar presente y ser igual al total de cajas de la orden para ese producto
        self.assertIn("amount_boxes", item_create)
        self.assertEqual(item_create["amount_boxes"], 7)

        # Actualizar la misma orden con otro total de cajas y verificar amount_boxes en la respuesta
        po_id = res_create.data["id"]
        patch_url = f"/api/purchase-orders/{po_id}/"
        payload_patch = {
            "items": [
                {"product": self.product2.id, "quantity_units": 3, "unit_type": "boxes", "amount_boxes": 3},
            ]
        }
        res_patch = self.client.patch(patch_url, data=payload_patch, format="json")
        self.assertIn(res_patch.status_code, (status.HTTP_200_OK, status.HTTP_202_ACCEPTED))
        self.assertGreaterEqual(len(res_patch.data.get("items", [])), 1)
        item_patch = res_patch.data["items"][0]
        self.assertIn("amount_boxes", item_patch)
        self.assertEqual(item_patch["amount_boxes"], 3)

    def test_list_purchase_orders_with_date_no_results_returns_message(self):
        # Asegurarnos de que no haya órdenes en una fecha futura
        from django.utils import timezone
        from datetime import timedelta
        future_day = (timezone.now() + timedelta(days=30)).date().isoformat()

        url = f"/api/purchase-orders/by-day/?date={future_day}"
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        # Debe devolver un objeto con 'detail' y no una lista vacía
        self.assertIsInstance(res.data, dict)
        self.assertIn("detail", res.data)
        self.assertEqual(res.data["detail"], "No existen órdenes para el día seleccionado.")

    def test_purchase_order_queryset_invalid_date_returns_all(self):
        # Crear 2 órdenes hoy
        url = "/api/purchase-orders/"
        for _ in range(2):
            payload = {
                "provider": self.provider.id,
                "ordered_by": self.user.id,
                "status": "PLACED",
                "items": [
                    {"product": self.product2.id, "quantity_units": 1, "unit_type": "boxes", "amount_boxes": 1},
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
        from datetime import timedelta, time

        # Crear otro proveedor
        other_provider = Provider.objects.create(
            name="Proveedor C",
            order_deadline_time=time(17, 0),
            order_available_weekdays=[1, 2, 3]
        )

        # Crear dos órdenes hoy: una para provider principal (más antigua) y otra para el otro provider (más reciente)
        po1 = PurchaseOrder.objects.create(provider=self.provider, ordered_by=self.user, status="PLACED")
        po2 = PurchaseOrder.objects.create(provider=other_provider, ordered_by=self.user, status="PLACED")

        # Ajustar created_at para que po1 sea más antigua que po2
        older = timezone.now() - timedelta(hours=1)
        PurchaseOrder.objects.filter(id=po1.id).update(created_at=older)

        day = timezone.now().date().isoformat()

        # Filtro por provider principal -> debe devolver po1
        res_main = self.client.get(f"/api/purchase-orders/by-day/?date={day}&provider={self.provider.id}")
        self.assertEqual(res_main.status_code, status.HTTP_200_OK)
        self.assertIsInstance(res_main.data, dict)
        self.assertEqual(res_main.data.get("provider"), self.provider.id)

        # Filtro por otro provider -> debe devolver po2 (la más reciente de ese provider)
        res_other = self.client.get(f"/api/purchase-orders/by-day/?date={day}&provider={other_provider.id}")
        self.assertEqual(res_other.status_code, status.HTTP_200_OK)
        self.assertIsInstance(res_other.data, dict)
        self.assertEqual(res_other.data.get("provider"), other_provider.id)

        # provider inválido -> 400
        res_bad = self.client.get(f"/api/purchase-orders/by-day/?date={day}&provider=abc")
        self.assertEqual(res_bad.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", res_bad.data)

    def test_last_shipped_returns_latest_for_authenticated_user(self):
        from django.utils import timezone
        from datetime import timedelta

        # Crear dos órdenes SHIPPED para el usuario autenticado
        po1 = PurchaseOrder.objects.create(provider=self.provider, ordered_by=self.user, status="SHIPPED")
        po2 = PurchaseOrder.objects.create(provider=self.provider, ordered_by=self.user, status="SHIPPED")

        # Forzar que po2 sea la más reciente por updated_at
        newer = timezone.now()
        older = newer - timedelta(minutes=5)
        PurchaseOrder.objects.filter(id=po1.id).update(updated_at=older)
        PurchaseOrder.objects.filter(id=po2.id).update(updated_at=newer)

        url = "/api/purchase-orders/last-shipped/"
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIsInstance(res.data, dict)
        self.assertEqual(res.data.get("id"), po2.id)

    def test_last_shipped_filters_by_provider(self):
        from django.utils import timezone
        from datetime import timedelta, time

        other_provider = Provider.objects.create(
            name="Proveedor Z",
            order_deadline_time=time(18, 0),
            order_available_weekdays=[0, 2, 4]
        )

        # Órdenes SHIPPED para distintos proveedores
        po_main = PurchaseOrder.objects.create(provider=self.provider, ordered_by=self.user, status="SHIPPED")
        po_other = PurchaseOrder.objects.create(provider=other_provider, ordered_by=self.user, status="SHIPPED")

        # Asegurar que ambas tengan updated_at distinto
        now = timezone.now()
        PurchaseOrder.objects.filter(id=po_main.id).update(updated_at=now)
        PurchaseOrder.objects.filter(id=po_other.id).update(updated_at=now)

        base_url = "/api/purchase-orders/last-shipped/"

        # Filtro por provider principal
        res_main = self.client.get(f"{base_url}?provider={self.provider.id}")
        self.assertEqual(res_main.status_code, status.HTTP_200_OK)
        self.assertIsInstance(res_main.data, dict)
        self.assertEqual(res_main.data.get("provider"), self.provider.id)

        # Filtro por otro provider
        res_other = self.client.get(f"{base_url}?provider={other_provider.id}")
        self.assertEqual(res_other.status_code, status.HTTP_200_OK)
        self.assertIsInstance(res_other.data, dict)
        self.assertEqual(res_other.data.get("provider"), other_provider.id)

    def test_last_shipped_no_results_returns_message(self):
        # No hay órdenes SHIPPED del usuario
        url = "/api/purchase-orders/last-shipped/"
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIsInstance(res.data, dict)
        self.assertEqual(res.data.get("detail"), "No existen órdenes enviadas.")

        # Crear una orden SHIPPED de otro usuario para verificar que no se devuelve
        User = get_user_model()
        other_user = User.objects.create_user(username="other", password="pass")
        PurchaseOrder.objects.create(provider=self.provider, ordered_by=other_user, status="SHIPPED")

        res2 = self.client.get(url)
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        self.assertEqual(res2.data.get("detail"), "No existen órdenes enviadas.")

    def test_last_shipped_invalid_provider_param_returns_400(self):
        url = "/api/purchase-orders/last-shipped/?provider=abc"
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", res.data)

    # --- Tests para la acción received-products ---
    def test_received_products_success_with_ids(self):
        # Crear orden SHIPPED con ítems para el usuario y proveedor principal
        po = PurchaseOrder.objects.create(provider=self.provider, ordered_by=self.user, status="SHIPPED")
        PurchaseOrderItem.objects.create(order=po, product=self.product1, quantity_units=2)
        PurchaseOrderItem.objects.create(order=po, product=self.product2, quantity_units=3)

        url = f"/api/purchase-orders/received-products/?provider={self.provider.id}"
        # Marcar solo product1 como recibido
        payload = {"products": [self.product1.id]}
        res = self.client.post(url, data=payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIsInstance(res.data, list)
        # Debe devolver ambos productos de la orden
        self.assertEqual(len(res.data), 2)
        by_id = {row["id"]: row for row in res.data}
        self.assertTrue(by_id[self.product1.id]["received"])  # recibido
        self.assertFalse(by_id[self.product1.id]["missing"])  # no falta
        self.assertFalse(by_id[self.product2.id]["received"])  # no recibido
        self.assertTrue(by_id[self.product2.id]["missing"])   # falta

    def test_received_products_success_with_barcodes(self):
        # Crear barcodes para los productos
        bc1 = ProductBarcode.objects.create(product=self.product1, code="BC-111", type=ProductBarcode.BarcodeType.EAN13)
        bc2 = ProductBarcode.objects.create(product=self.product2, code="BC-222", type=ProductBarcode.BarcodeType.EAN13)

        # Crear orden SHIPPED con ítems para el usuario
        po = PurchaseOrder.objects.create(provider=self.provider, ordered_by=self.user, status="SHIPPED")
        PurchaseOrderItem.objects.create(order=po, product=self.product1, quantity_units=5)
        PurchaseOrderItem.objects.create(order=po, product=self.product2, quantity_units=7)

        url = f"/api/purchase-orders/received-products/?provider={self.provider.id}"
        # Enviar barcodes en lugar de IDs, marcar ambos como recibidos
        payload = {"products": [bc1.code, bc2.code]}
        res = self.client.post(url, data=payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIsInstance(res.data, list)
        self.assertEqual(len(res.data), 2)
        for row in res.data:
            self.assertTrue(row["received"])  # ambos recibidos
            self.assertFalse(row["missing"])  # ninguno falta

    def test_received_products_missing_provider_returns_400(self):
        url = "/api/purchase-orders/received-products/"
        res = self.client.post(url, data={"products": []}, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", res.data)

    def test_received_products_invalid_provider_returns_400(self):
        url = "/api/purchase-orders/received-products/?provider=abc"
        res = self.client.post(url, data={"products": []}, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", res.data)

    def test_received_products_no_shipped_returns_message(self):
        # No existe orden SHIPPED para el proveedor
        url = f"/api/purchase-orders/received-products/?provider={self.provider.id}"
        res = self.client.post(url, data={"products": [self.product1.id]}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIsInstance(res.data, dict)
        self.assertEqual(res.data.get("detail"), "No existen órdenes enviadas para este proveedor.")

    def test_received_products_products_not_list_returns_400(self):
        # Crear una orden SHIPPED para pasar la validación de existencia
        PurchaseOrder.objects.create(provider=self.provider, ordered_by=self.user, status="SHIPPED")
        url = f"/api/purchase-orders/received-products/?provider={self.provider.id}"
        # Enviar un dict en lugar de lista
        res = self.client.post(url, data={"products": {"a": 1}}, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", res.data)

    def test_provider_has_received_orders_flag(self):
        """Test que el campo has_received_orders funcione correctamente en ProviderSerializer."""
        # Inicialmente, el proveedor no debe tener órdenes RECEIVED
        url = f"/api/providers/{self.provider.id}/"
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertFalse(res.data.get("has_received_orders"))

        # Crear una orden en estado PLACED (no RECEIVED)
        po_placed = PurchaseOrder.objects.create(
            provider=self.provider, 
            ordered_by=self.user, 
            status=PurchaseOrder.Status.PLACED
        )
        
        # El flag debe seguir siendo False
        res2 = self.client.get(url)
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        self.assertFalse(res2.data.get("has_received_orders"))

        # Crear una orden en estado RECEIVED
        po_received = PurchaseOrder.objects.create(
            provider=self.provider, 
            ordered_by=self.user, 
            status=PurchaseOrder.Status.RECEIVED
        )
        
        # Ahora el flag debe ser True
        res3 = self.client.get(url)
        self.assertEqual(res3.status_code, status.HTTP_200_OK)
        self.assertTrue(res3.data.get("has_received_orders"))

        # Verificar también en la lista de proveedores
        list_url = "/api/providers/"
        res_list = self.client.get(list_url)
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        provider_data = next((p for p in res_list.data if p["id"] == self.provider.id), None)
        self.assertIsNotNone(provider_data)
        self.assertTrue(provider_data.get("has_received_orders"))

    def test_provider_order_schedule_fields(self):
        """Test que verifica que los campos de horario de pedidos se devuelven correctamente."""
        from datetime import time

        # Configurar proveedor con días laborales (Lun-Vie) y hora límite 14:30
        self.provider.order_available_weekdays = [0, 1, 2, 3, 4]  # Lun-Vie
        self.provider.order_deadline_time = time(14, 30)
        self.provider.save()

        url = f"/api/providers/{self.provider.id}/"
        res = self.client.get(url)

        self.assertEqual(res.status_code, status.HTTP_200_OK)

        # Verificar que los campos están presentes en la respuesta
        self.assertIn("order_deadline_time", res.data)
        self.assertIn("order_available_weekdays", res.data)

        # Verificar valores correctos
        self.assertEqual(res.data["order_deadline_time"], "14:30:00")
        self.assertEqual(res.data["order_available_weekdays"], [0, 1, 2, 3, 4])

        # Verificar que el campo order_available_dates está presente
        self.assertIn("order_available_dates", res.data)
        self.assertIsInstance(res.data["order_available_dates"], list)

        # Verificar también en la lista de proveedores
        list_url = "/api/providers/"
        res_list = self.client.get(list_url)
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)

        provider_data = next((p for p in res_list.data if p["id"] == self.provider.id), None)
        self.assertIsNotNone(provider_data)
        self.assertEqual(provider_data["order_deadline_time"], "14:30:00")
        self.assertEqual(provider_data["order_available_weekdays"], [0, 1, 2, 3, 4])

    def test_provider_order_schedule_required_fields(self):
        """Test que verifica que ambos campos de horario son requeridos y se devuelven correctamente."""
        from datetime import time

        # Configurar proveedor con todos los campos requeridos
        self.provider.order_available_weekdays = [1, 2, 3]  # Mar-Jue
        self.provider.order_deadline_time = time(16, 0)  # 16:00
        self.provider.save()

        url = f"/api/providers/{self.provider.id}/"
        res = self.client.get(url)

        self.assertEqual(res.status_code, status.HTTP_200_OK)

        # Verificar que ambos campos están presentes y son requeridos
        self.assertEqual(res.data["order_deadline_time"], "16:00:00")
        self.assertEqual(res.data["order_available_weekdays"], [1, 2, 3])

        # Verificar que no pueden ser nulos
        self.assertIsNotNone(res.data["order_deadline_time"])
        self.assertIsNotNone(res.data["order_available_weekdays"])

    def test_provider_order_available_dates_format(self):
        """Test que verifica el formato correcto de las fechas en order_available_dates."""
        from datetime import time, datetime
        import re

        # Configurar proveedor con días específicos
        self.provider.order_available_weekdays = [1, 3, 5]  # Martes, Jueves, Sábado
        self.provider.order_deadline_time = time(15, 0)
        self.provider.save()

        url = f"/api/providers/{self.provider.id}/"
        res = self.client.get(url)

        self.assertEqual(res.status_code, status.HTTP_200_OK)

        # Verificar que el campo existe y es una lista
        self.assertIn("order_available_dates", res.data)
        dates = res.data["order_available_dates"]
        self.assertIsInstance(dates, list)

        # Patrón regex para formato "Día DD/MM/YYYY"
        date_pattern = re.compile(r'^(Lunes|Martes|Miércoles|Jueves|Viernes|Sábado|Domingo) \d{2}/\d{2}/\d{4}$')

        # Verificar que todas las fechas tienen el formato correcto
        for date_str in dates:
            self.assertIsInstance(date_str, str)
            self.assertTrue(date_pattern.match(date_str), 
                          f"Fecha '{date_str}' no tiene el formato 'Día DD/MM/YYYY'")

        # Verificar que las fechas están ordenadas cronológicamente
        if len(dates) > 1:
            # Extraer solo las fechas para comparar cronológicamente
            date_objects = []
            for date_str in dates:
                date_part = date_str.split(' ')[1]  # Obtener "DD/MM/YYYY"
                date_obj = datetime.strptime(date_part, '%d/%m/%Y').date()
                date_objects.append(date_obj)

            for i in range(1, len(date_objects)):
                self.assertGreater(date_objects[i], date_objects[i-1], 
                                 "Las fechas deben estar ordenadas cronológicamente")

        # Verificar que no hay fechas duplicadas
        self.assertEqual(len(dates), len(set(dates)), 
                        "No debe haber fechas duplicadas")

        # Verificar que las fechas corresponden a los días configurados
        for date_str in dates:
            # Extraer solo la parte de la fecha del string "Día DD/MM/YYYY"
            date_part = date_str.split(' ')[1]  # Obtener "DD/MM/YYYY"
            date_obj = datetime.strptime(date_part, '%d/%m/%Y').date()
            weekday = date_obj.weekday()
            self.assertIn(weekday, self.provider.order_available_weekdays,
                         f"La fecha {date_str} (día {weekday}) no está en los días configurados")
            
            # Verificar que el nombre del día coincide con el weekday
            day_name = date_str.split(' ')[0]  # Obtener "Día"
            expected_names = {
                0: 'Lunes', 1: 'Martes', 2: 'Miércoles', 3: 'Jueves',
                4: 'Viernes', 5: 'Sábado', 6: 'Domingo'
            }
            self.assertEqual(day_name, expected_names[weekday],
                           f"El nombre del día '{day_name}' no coincide con el weekday {weekday}")

    def test_products_ordering_parameter(self):
        """Test que verifica el parámetro ordering en el endpoint de productos."""
        # Crear productos adicionales para probar ordenamiento
        Product.objects.create(name="Zebra Product", sku="SKU-Z")
        Product.objects.create(name="Alpha Product", sku="SKU-A")
        
        # Test 1: Ordenamiento ascendente por nombre (por defecto)
        url = "/api/products/"
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        names = [product["name"] for product in res.data]
        self.assertEqual(names, sorted(names))  # Debe estar ordenado ascendente
        
        # Test 2: Ordenamiento ascendente explícito
        url = "/api/products/?ordering=name"
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        names = [product["name"] for product in res.data]
        self.assertEqual(names, sorted(names))  # Debe estar ordenado ascendente
        
        # Test 3: Ordenamiento descendente por nombre
        url = "/api/products/?ordering=-name"
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        names = [product["name"] for product in res.data]
        self.assertEqual(names, sorted(names, reverse=True))  # Debe estar ordenado descendente
