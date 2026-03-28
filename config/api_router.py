from django.conf import settings
from rest_framework.routers import DefaultRouter
from rest_framework.routers import SimpleRouter
from clients.views import ClientViewSet
from sales_orders.views import CustomerOrderViewSet, CustomerOrderItemViewSet


from kachadigitalbcn.users.api.views import UserViewSet
from market.refrigerator_views import RefrigeratorViewSet, TemperatureRecordViewSet
from purchase_orders.views import PurchaseOrderViewSet, PurchaseOrderItemViewSet
from received.views import SearchReceivedProductViewSet, ReceptionViewSet
from invoice_parser.views import InvoiceParserViewSet

router = DefaultRouter() if settings.DEBUG else SimpleRouter()

router.register("users", UserViewSet)
router.register("refrigerators", RefrigeratorViewSet)
router.register("temperature-records", TemperatureRecordViewSet, basename="temperaturerecord")
router.register("purchase-orders", PurchaseOrderViewSet, basename="purchaseorder")
router.register("purchase-order-items", PurchaseOrderItemViewSet, basename="purchaseorderitem")
router.register("received-products", SearchReceivedProductViewSet, basename="receivedproduct")
router.register("receptions", ReceptionViewSet, basename="reception")
router.register("invoice-parser", InvoiceParserViewSet, basename="invoiceparser")
router.register(r"clients", ClientViewSet, basename="clients")
router.register(r"customer-orders", CustomerOrderViewSet, basename="customer-orders")
router.register(r"customer-order-items", CustomerOrderItemViewSet, basename="customer-order-items")

app_name = "api"
urlpatterns = router.urls
