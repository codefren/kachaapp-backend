from django.urls import path, include
from rest_framework.routers import DefaultRouter

from . import views

app_name = "proveedores"

router = DefaultRouter()
router.register(r"products", views.ProductViewSet, basename="product")
router.register(r"providers", views.ProviderViewSet, basename="provider")

urlpatterns = [
    path("", views.proveedores_root, name="root"),
    path("", include(router.urls)),
]
