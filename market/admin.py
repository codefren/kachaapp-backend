from django.contrib import admin

from .models import Market, Shift


@admin.register(Market)
class MarketAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "latitude", "longitude")
    search_fields = ("name", "organization__name")


@admin.register(Shift)
class ShiftAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "market",
        "started_at",
        "ended_at",
        "estado",
        "break_started_at",
        "break_total_seconds",
    )
    list_filter = ("market", "started_at", "ended_at")
    search_fields = ("user__username", "market__name")
    readonly_fields = ("created_at", "updated_at")

    @admin.display(description="Estado")
    def estado(self, obj):
        if obj.ended_at:
            return "Finalizada"
        if obj.on_break:
            return "En descanso"
        return "Trabajando"
