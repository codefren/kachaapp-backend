from django.utils import timezone
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters import rest_framework as filters

from kachadigitalbcn.users.mixins import (
    OrganizationQuerySetMixin,
    OrganizationPermissionMixin
)

from .models import Refrigerator, TemperatureRecord
from .refrigerator_serializers import (
    RefrigeratorSerializer,
    TemperatureRecordSerializer,
)


class RefrigeratorViewSet(OrganizationQuerySetMixin, OrganizationPermissionMixin, viewsets.ModelViewSet):
    """CRUD de neveras con filtrado automático por organización."""

    queryset = Refrigerator.objects.all().select_related("market")
    serializer_class = RefrigeratorSerializer
    permission_classes = [permissions.IsAuthenticated]
    organization_field_path = 'market__organization'  # Refrigerator -> Market -> Organization

    def get_queryset(self):
        # Filtrar primero por organización
        qs = super().get_queryset()
        # Luego aplicar filtros adicionales
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


class TemperatureRecordFilter(filters.FilterSet):
    """Filtros para registros de temperatura."""
    market = filters.NumberFilter(field_name='refrigerator__market', label='Market ID')
    date = filters.DateFilter(field_name='date', label='Fecha (YYYY-MM-DD)')
    date_from = filters.DateFilter(field_name='date', lookup_expr='gte', label='Fecha desde')
    date_to = filters.DateFilter(field_name='date', lookup_expr='lte', label='Fecha hasta')
    period = filters.ChoiceFilter(choices=TemperatureRecord.Period.choices, label='Período del día')
    refrigerator = filters.NumberFilter(field_name='refrigerator', label='Refrigerador ID')

    class Meta:
        model = TemperatureRecord
        fields = ['market', 'date', 'date_from', 'date_to', 'period', 'refrigerator']


class TemperatureRecordViewSet(OrganizationQuerySetMixin, viewsets.ReadOnlyModelViewSet):
    """ViewSet para consultar registros de temperatura con filtrado automático por organización."""
    queryset = TemperatureRecord.objects.all().select_related(
        'refrigerator', 'refrigerator__market'
    ).order_by('-date', '-recorded_at')
    serializer_class = TemperatureRecordSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_class = TemperatureRecordFilter
    filter_backends = [filters.DjangoFilterBackend]
    organization_field_path = 'refrigerator__market__organization'  # TemperatureRecord -> Refrigerator -> Market -> Organization

    def get_queryset(self):
        """Filtrar por organización y optimizar queryset."""
        # El mixin ya filtra por organización a través de refrigerator__market__organization
        qs = super().get_queryset()
        return qs
