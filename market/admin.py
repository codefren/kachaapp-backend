from django.contrib import admin
from .models import Market, Refrigerator, TemperatureRecord

@admin.register(Market)
class MarketAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "latitude", "longitude")
    list_filter = ("organization",)
    search_fields = ("name",)
    autocomplete_fields = ("organization",)



class TemperatureRecordInline(admin.TabularInline):
    model = TemperatureRecord
    extra = 0
    readonly_fields = ("date", "temperature", "recorded_at")
    can_delete = False


@admin.register(Refrigerator)
class RefrigeratorAdmin(admin.ModelAdmin):
    list_display = ("name", "market", "created_at")
    list_filter = ("market",)
    search_fields = ("name", "market__name")
    inlines = [TemperatureRecordInline]


@admin.register(TemperatureRecord)
class TemperatureRecordAdmin(admin.ModelAdmin):
    list_display = ("refrigerator", "date", "temperature", "recorded_at")
    list_filter = ("refrigerator__market", "date")
    search_fields = ("refrigerator__name",)

# Register your models here.
