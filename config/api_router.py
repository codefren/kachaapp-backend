from django.conf import settings
from rest_framework.routers import DefaultRouter
from rest_framework.routers import SimpleRouter

from kachadigitalbcn.users.api.views import UserViewSet
from market.refrigerator_views import RefrigeratorViewSet, TemperatureRecordViewSet
from purchase_orders.views import PurchaseOrderViewSet, PurchaseOrderItemViewSet
from received.views import SearchReceivedProductViewSet, ReceptionViewSet

router = DefaultRouter() if settings.DEBUG else SimpleRouter()

router.register("users", UserViewSet)
router.register("refrigerators", RefrigeratorViewSet)
router.register("temperature-records", TemperatureRecordViewSet, basename="temperaturerecord")
router.register("purchase-orders", PurchaseOrderViewSet, basename="purchaseorder")
router.register("purchase-order-items", PurchaseOrderItemViewSet, basename="purchaseorderitem")
router.register("received-products", SearchReceivedProductViewSet, basename="receivedproduct")
router.register("receptions", ReceptionViewSet, basename="reception")


app_name = "api"
urlpatterns = router.urls
