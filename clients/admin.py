from django.contrib import admin

from .models import Client


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "client_type", "is_active", "created_at")
    search_fields = ("name", "phone", "address")
    list_filter = ("client_type", "is_active", "created_at")
