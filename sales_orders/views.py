from datetime import datetime, time, timedelta
import os

import requests
from rest_framework import permissions, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import CustomerOrder, CustomerOrderItem
from .serializers import CustomerOrderSerializer, CustomerOrderItemSerializer


class CustomerOrderViewSet(viewsets.ModelViewSet):
    queryset = (
        CustomerOrder.objects
        .select_related("client", "created_by", "route")
        .prefetch_related("items", "items__product")
        .order_by("route_order", "-created_at")
    )
    serializer_class = CustomerOrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class CustomerOrderItemViewSet(viewsets.ModelViewSet):
    queryset = (
        CustomerOrderItem.objects
        .select_related("order", "product")
        .order_by("-created_at")
    )
    serializer_class = CustomerOrderItemSerializer
    permission_classes = [permissions.IsAuthenticated]


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def delivery_slots(request):
    date_str = request.GET.get("date")

    if not date_str:
        return Response({"error": "date requerido"}, status=400)

    try:
        date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return Response({"error": "date inválido, usa YYYY-MM-DD"}, status=400)

    weekday = date.weekday()  # lunes=0, domingo=6

    if weekday <= 4:
        start_hour = 8
        end_hour = 20
    else:
        start_hour = 10
        end_hour = 13

    slots = []
    current = time(hour=start_hour)

    while current.hour < end_hour:
        next_hour = (datetime.combine(date, current) + timedelta(hours=1)).time()

        count = CustomerOrder.objects.filter(
            delivery_required=True,
            delivery_date=date,
            delivery_time_from=current,
            status__in=[
                CustomerOrder.Status.CONFIRMED,
                CustomerOrder.Status.PREPARING,
                CustomerOrder.Status.READY,
                CustomerOrder.Status.OUT_FOR_DELIVERY,
            ],
        ).count()

        capacity = 6
        available = count < capacity

        slots.append(
            {
                "from": current.strftime("%H:%M"),
                "to": next_hour.strftime("%H:%M"),
                "count": count,
                "capacity": capacity,
                "available": available,
            }
        )

        current = next_hour

    return Response(slots)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def google_route_preview(request):
    stops = request.data.get("stops", [])

    if not isinstance(stops, list) or len(stops) < 2:
        return Response(
            {"detail": "Debes enviar al menos origen y destino."},
            status=400,
        )

    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        return Response(
            {"detail": "Falta GOOGLE_MAPS_API_KEY en el backend."},
            status=500,
        )

    try:
        origin = stops[0]
        destination = stops[-1]
        intermediates = stops[1:-1]

        def waypoint(stop):
            return {
                "location": {
                    "latLng": {
                        "latitude": float(stop["latitude"]),
                        "longitude": float(stop["longitude"]),
                    }
                }
            }

        payload = {
            "origin": waypoint(origin),
            "destination": waypoint(destination),
            "intermediates": [waypoint(s) for s in intermediates],
            "travelMode": "DRIVE",
            "routingPreference": "TRAFFIC_AWARE",
            "optimizeWaypointOrder": True,
            "polylineQuality": "OVERVIEW",
            "polylineEncoding": "ENCODED_POLYLINE",
            "languageCode": "es-ES",
            "units": "METRIC",
        }

        res = requests.post(
            "https://routes.googleapis.com/directions/v2:computeRoutes",
            json=payload,
            headers={
                "Content-Type": "application/json",
                "X-Goog-Api-Key": api_key,
                "X-Goog-FieldMask": (
                    "routes.distanceMeters,"
                    "routes.duration,"
                    "routes.polyline.encodedPolyline,"
                    "routes.optimizedIntermediateWaypointIndex,"
                    "routes.viewport"
                ),
            },
            timeout=20,
        )

        if res.status_code >= 400:
            return Response(
                {
                    "detail": "Google Routes API devolvió error.",
                    "status_code": res.status_code,
                    "google_error": res.text,
                },
                status=502,
            )

        data = res.json()
        routes = data.get("routes", [])

        if not routes:
            return Response(
                {"detail": "Google no devolvió rutas."},
                status=502,
            )

        route = routes[0]

        return Response(
            {
                "distanceMeters": route.get("distanceMeters"),
                "duration": route.get("duration"),
                "encodedPolyline": route.get("polyline", {}).get("encodedPolyline"),
                "optimizedIntermediateWaypointIndex": route.get(
                    "optimizedIntermediateWaypointIndex", []
                ),
                "viewport": route.get("viewport"),
            }
        )

    except Exception as e:
        return Response(
            {"detail": "Error generando ruta.", "error": str(e)},
            status=500,
        )
