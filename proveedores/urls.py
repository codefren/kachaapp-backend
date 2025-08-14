from django.urls import path

from . import views

app_name = "proveedores"

urlpatterns = [
    path("", views.proveedores_root, name="root"),
]
