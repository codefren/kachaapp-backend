from django.conf import settings
from django.urls import path
from rest_framework.routers import DefaultRouter, SimpleRouter

from clients.views import ClientViewSet
from invoice_parser.views import InvoiceParserViewSet
from kachadigitalbcn.users.api.views import UserViewSet
from market.refrigerator_views import RefrigeratorViewSet, TemperatureRecordViewSet
from purchase_orders.views import PurchaseOrderViewSet, PurchaseOrderItemViewSet
from received.views import SearchReceivedProductViewSet, ReceptionViewSet
from sales_orders.views import (
    CustomerOrderItemViewSet,
    CustomerOrderViewSet,
    delivery_slots,
    google_route_preview,
)

router = DefaultRouter() if settings.DEBUG else SimpleRouter()

router.register("users", UserViewSet)
router.register("refrigerators", RefrigeratorViewSet)
router.register("temperature-records", TemperatureRecordViewSet, basename="temperaturerecord")
router.register("purchase-orders", PurchaseOrderViewSet, basename="purchaseorder")
router.register("purchase-order-items", PurchaseOrderItemViewSet, basename="purchaseorderitem")
router.register("received-products", SearchReceivedProductViewSet, basename="receivedproduct")
router.register("receptions", ReceptionViewSet, basename="reception")
router.register("invoice-parser", InvoiceParserViewSet, basename="invoiceparser")
router.register("clients", ClientViewSet, basename="clients")
router.register("customer-orders", CustomerOrderViewSet, basename="customer-orders")
router.register("customer-order-items", CustomerOrderItemViewSet, basename="customer-order-items")

app_name = "api"

urlpatterns = router.urls + [
    path("delivery/slots/", delivery_slots, name="delivery-slots"),
    path("delivery/google-route/", google_route_preview, name="delivery-google-route"),
]
