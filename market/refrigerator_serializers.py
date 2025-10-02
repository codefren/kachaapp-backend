from rest_framework import serializers
from django.utils import timezone
from drf_spectacular.utils import extend_schema_field

from .models import Refrigerator, TemperatureRecord


class TemperatureRecordSerializer(serializers.ModelSerializer):
    temperature_status = serializers.SerializerMethodField()
    is_critical = serializers.SerializerMethodField()
    period_display = serializers.SerializerMethodField()

    class Meta:
        model = TemperatureRecord
        fields = (
            "id",
            "refrigerator",
            "date",
            "period",
            "period_display",
            "temperature",
            "temperature_status",
            "is_critical",
            "recorded_at",
        )
        read_only_fields = ("recorded_at",)

    def validate_temperature(self, value):
        """Validar que la temperatura esté en el rango permitido para neveras."""
        if value is not None:
            if value < -30.0 or value > 10.0:
                raise serializers.ValidationError(
                    "La temperatura debe estar entre -30°C y 10°C para una nevera."
                )
        return value

    def validate(self, attrs):
        """Validaciones a nivel de objeto."""
        # Verificar que no exista ya un registro para la misma nevera, fecha y período
        refrigerator = attrs.get("refrigerator")
        date = attrs.get("date")
        period = attrs.get("period")

        if refrigerator and date and period:
            # Si estamos actualizando, excluir el objeto actual
            queryset = TemperatureRecord.objects.filter(
                refrigerator=refrigerator, date=date, period=period
            )

            if self.instance:
                queryset = queryset.exclude(pk=self.instance.pk)

            if queryset.exists():
                raise serializers.ValidationError(
                    "Ya existe un registro de temperatura para esta nevera, fecha y período."
                )

        return attrs

    @extend_schema_field(serializers.CharField())
    def get_temperature_status(self, obj):
        """Retorna el estado de la temperatura."""
        return obj.get_temperature_status()

    @extend_schema_field(serializers.BooleanField())
    def get_is_critical(self, obj):
        """Retorna si la temperatura es crítica."""
        return obj.is_temperature_critical()

    @extend_schema_field(serializers.CharField())
    def get_period_display(self, obj):
        """Retorna el nombre legible del período."""
        return obj.get_period_display()


class RefrigeratorSerializer(serializers.ModelSerializer):
    """Incluye solo las temperaturas del día actual por período."""

    morning_temperature = serializers.SerializerMethodField()
    night_temperature = serializers.SerializerMethodField()

    class Meta:
        model = Refrigerator
        fields = (
            "id",
            "market",
            "name",
            "morning_temperature",
            "night_temperature",
            "created_at",
        )
        read_only_fields = ("created_at",)

    @extend_schema_field(TemperatureRecordSerializer(allow_null=True))
    def get_morning_temperature(self, obj):
        """Retorna la temperatura de mañana del día actual."""
        today = timezone.localdate()
        try:
            record = obj.temperature_records.get(
                period=TemperatureRecord.Period.MORNING, date=today
            )
            return {
                "id": record.id,
                "date": record.date,
                "temperature": record.temperature,
                "period": record.period,
                "is_critical": record.is_temperature_critical(),
                "recorded_at": record.recorded_at,
            }
        except TemperatureRecord.DoesNotExist:
            return None

    @extend_schema_field(TemperatureRecordSerializer(allow_null=True))
    def get_night_temperature(self, obj):
        """Retorna la temperatura de noche del día actual."""
        today = timezone.localdate()
        try:
            record = obj.temperature_records.get(
                period=TemperatureRecord.Period.NIGHT, date=today
            )
            return {
                "id": record.id,
                "date": record.date,
                "temperature": record.temperature,
                "period": record.period,
                "is_critical": record.is_temperature_critical(),
                "recorded_at": record.recorded_at,
            }
        except TemperatureRecord.DoesNotExist:
            return None
