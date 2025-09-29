from rest_framework import serializers
from django.utils import timezone

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
            "recorded_at"
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
        refrigerator = attrs.get('refrigerator')
        date = attrs.get('date')
        period = attrs.get('period')
        
        if refrigerator and date and period:
            # Si estamos actualizando, excluir el objeto actual
            queryset = TemperatureRecord.objects.filter(
                refrigerator=refrigerator,
                date=date,
                period=period
            )
            
            if self.instance:
                queryset = queryset.exclude(pk=self.instance.pk)
            
            if queryset.exists():
                raise serializers.ValidationError(
                    "Ya existe un registro de temperatura para esta nevera, fecha y período."
                )
        
        return attrs

    def get_temperature_status(self, obj):
        """Retorna el estado de la temperatura."""
        return obj.get_temperature_status()

    def get_is_critical(self, obj):
        """Retorna si la temperatura es crítica."""
        return obj.is_temperature_critical()

    def get_period_display(self, obj):
        """Retorna el nombre legible del período."""
        return obj.get_period_display()


class RefrigeratorSerializer(serializers.ModelSerializer):
    """Incluye las listas de temperaturas por período."""

    morning_temperatures = serializers.SerializerMethodField()
    night_temperatures = serializers.SerializerMethodField()

    class Meta:
        model = Refrigerator
        fields = (
            "id", 
            "market", 
            "name", 
            "morning_temperatures",
            "night_temperatures",
            "created_at"
        )
        read_only_fields = ("created_at",)

    def get_morning_temperatures(self, obj):
        """Retorna lista de todas las temperaturas de mañana ordenadas por fecha."""
        morning_records = obj.temperature_records.filter(
            period=TemperatureRecord.Period.MORNING
        ).order_by('-date')
        
        return [
            {
                "id": record.id,
                "date": record.date,
                "temperature": record.temperature,
                "status": record.get_temperature_status(),
                "is_critical": record.is_temperature_critical(),
                "recorded_at": record.recorded_at
            }
            for record in morning_records
        ]

    def get_night_temperatures(self, obj):
        """Retorna lista de todas las temperaturas de noche ordenadas por fecha."""
        night_records = obj.temperature_records.filter(
            period=TemperatureRecord.Period.NIGHT
        ).order_by('-date')
        
        return [
            {
                "id": record.id,
                "date": record.date,
                "temperature": record.temperature,
                "status": record.get_temperature_status(),
                "is_critical": record.is_temperature_critical(),
                "recorded_at": record.recorded_at
            }
            for record in night_records
        ]
