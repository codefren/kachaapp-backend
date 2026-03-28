from django.contrib import admin

from .models import CustomerOrder, CustomerOrderItem


class CustomerOrderItemInline(admin.TabularInline):
    model = CustomerOrderItem
    extra = 0


@admin.register(CustomerOrder)
class CustomerOrderAdmin(admin.ModelAdmin):
    list_display = ("id", "client", "status", "created_by", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("client__name", "client__phone", "id")
    inlines = [CustomerOrderItemInline]


@admin.register(CustomerOrderItem)
class CustomerOrderItemAdmin(admin.ModelAdmin):
    list_display = ("id", "order", "product", "quantity", "created_at")
    list_filter = ("created_at",)
    search_fields = ("order__id", "product__name")
