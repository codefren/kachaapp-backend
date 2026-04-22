from django.urls import path
from . import views

urlpatterns = [
    path('me/status/', views.worker_status, name='worker_status'),
]
