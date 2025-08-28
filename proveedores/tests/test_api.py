from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status

from proveedores.models import Provider, Product, PurchaseOrder, PurchaseOrderItem, ProductFavorite


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
                {"product": self.product1.id, "quantity_units": 10, "unit_price": "1.50"},
                {"product": self.product2.id, "quantity_units": 5, "unit_price": "3.00"},
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
