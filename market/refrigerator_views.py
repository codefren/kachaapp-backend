from django.utils import timezone
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Refrigerator, TemperatureRecord
from .refrigerator_serializers import RefrigeratorSerializer, TemperatureRecordSerializer


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
        fridge = self.get_object()
        temp = request.data.get("temperature")
        try:
            temp_val = float(temp)
        except (TypeError, ValueError):
            return Response({"detail": "Valor de temperatura inválido"}, status=status.HTTP_400_BAD_REQUEST)

        today = timezone.localdate()
        record, _ = TemperatureRecord.objects.update_or_create(
            refrigerator=fridge, date=today, defaults={"temperature": temp_val}
        )
        return Response(TemperatureRecordSerializer(record).data, status=status.HTTP_200_OK)
