from django.utils import timezone
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Refrigerator, TemperatureRecord
from .refrigerator_serializers import (
    RefrigeratorSerializer,
    TemperatureRecordSerializer,
)


class RefrigeratorViewSet(viewsets.ModelViewSet):
    """CRUD de neveras + endpoint para registrar temperatura del día."""

    queryset = Refrigerator.objects.all().select_related("market")
    serializer_class = RefrigeratorSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        market_id = self.request.query_params.get("market")
        if market_id:
            qs = qs.filter(market_id=market_id)
        return qs

    @action(detail=True, methods=["put"], url_path="temperature")
    def update_temperature(self, request, pk=None):
        """Actualizar temperatura de una nevera para un período específico."""
        fridge = self.get_object()
        temp = request.data.get("temperature")
        period = request.data.get("period", TemperatureRecord.Period.MORNING)

        # Validar temperatura
        try:
            temp_val = float(temp)
        except (TypeError, ValueError):
            return Response(
                {"detail": "Valor de temperatura inválido"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validar período
        if period not in [choice[0] for choice in TemperatureRecord.Period.choices]:
            return Response(
                {
                    "detail": f"Período inválido. Opciones: {[choice[0] for choice in TemperatureRecord.Period.choices]}"
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        today = timezone.localdate()

        # Usar el serializer para validaciones completas
        data = {
            "refrigerator": fridge.id,
            "date": today,
            "period": period,
            "temperature": temp_val,
        }

        # Buscar registro existente
        try:
            existing_record = TemperatureRecord.objects.get(
                refrigerator=fridge, date=today, period=period
            )
            serializer = TemperatureRecordSerializer(
                existing_record, data=data, partial=True
            )
        except TemperatureRecord.DoesNotExist:
            serializer = TemperatureRecordSerializer(data=data)

        if serializer.is_valid():
            record = serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
