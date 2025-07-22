from rest_framework import serializers
from django.utils import timezone

from .models import Refrigerator, TemperatureRecord


class TemperatureRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = TemperatureRecord
        fields = ("id", "refrigerator", "date", "temperature", "recorded_at")
        read_only_fields = ("recorded_at",)


class RefrigeratorSerializer(serializers.ModelSerializer):
    """Incluye la temperatura de hoy (si la hay)."""

    today_temperature = serializers.SerializerMethodField()

    class Meta:
        model = Refrigerator
        fields = ("id", "market", "name", "today_temperature", "created_at")
        read_only_fields = ("created_at",)

    def get_today_temperature(self, obj):
        today = timezone.localdate()
        record = obj.temperature_records.filter(date=today).first()
        return record.temperature if record else 0.0
