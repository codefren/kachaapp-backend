import logging

from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView


from .models import LoginHistory, Market, Shift
from .serializers import (
    MarketProximityTokenObtainPairSerializer,
    MarketProximityTokenRefreshSerializer,
)

logger = logging.getLogger(__name__)


class MarketLoginHistoryMixin:
    def log_login_history(self, user, market, latitude, longitude, event_type):
        if user and getattr(user, "is_authenticated", False) and market:
            LoginHistory.objects.create(
                user=user,
                market=market,
                latitude=latitude,
                longitude=longitude,
                event_type=event_type,
            )


class MarketProximityTokenObtainPairView(MarketLoginHistoryMixin, TokenObtainPairView):
    serializer_class = MarketProximityTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        latitude = request.data.get("latitude")
        longitude = request.data.get("longitude")

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        market = getattr(serializer, "_market", None)
        user = getattr(serializer, "user", None)

        self.log_login_history(
            user,
            market,
            latitude,
            longitude,
            LoginHistory.LOGIN,
        )

        return Response(serializer.validated_data, status=status.HTTP_200_OK)


class MarketProximityTokenRefreshView(MarketLoginHistoryMixin, TokenRefreshView):
    serializer_class = MarketProximityTokenRefreshSerializer

    def post(self, request, *args, **kwargs):
        latitude = request.data.get("latitude")
        longitude = request.data.get("longitude")

        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            market = getattr(serializer, "_market", None)
            user = (
                request.user
                if getattr(request.user, "is_authenticated", False)
                else None
            )

            self.log_login_history(
                user,
                market,
                latitude,
                longitude,
                LoginHistory.REFRESH,
            )

            return Response(serializer.validated_data, status=status.HTTP_200_OK)

        except ValidationError as e:
            logger.warning(
                "[MarketProximity] Validation failed (refresh) lat=%s lon=%s errors=%s",
                latitude,
                longitude,
                getattr(e, "detail", str(e)),
            )
            raise
        except Exception:
            logger.exception("[MarketProximity] Error processing token refresh POST")
            raise


def _nearest_market(latitude, longitude, max_distance_meters=500):
    if latitude is None or longitude is None:
        return None

    try:
        lat = float(latitude)
        lon = float(longitude)
    except (TypeError, ValueError):
        return None

    for market in Market.objects.all():
        if market.is_near(lat, lon, max_distance_meters=max_distance_meters):
            return market

    return None


def _latest_market_for_user(user):
    last_login = (
        LoginHistory.objects.filter(user=user)
        .select_related("market")
        .order_by("-timestamp")
        .first()
    )
    return last_login.market if last_login else None


def _get_open_shift(user):
    return (
        Shift.objects.filter(user=user, ended_at__isnull=True)
        .select_related("market")
        .order_by("-started_at")
        .first()
    )


def _serialize_today_shift(shift):
    if not shift:
        return {
            "status": "OFF",
            "on_break": False,
            "market_name": None,
            "started_at": None,
            "ended_at": None,
            "worked_seconds": 0,
            "break_seconds": 0,
        }

    now = timezone.now()
    return {
        "status": "BREAK" if shift.on_break else "WORKING",
        "on_break": shift.on_break,
        "market_name": shift.market.name if shift.market else None,
        "started_at": shift.started_at.isoformat(),
        "ended_at": shift.ended_at.isoformat() if shift.ended_at else None,
        "worked_seconds": shift.get_worked_seconds(now=now),
        "break_seconds": shift.get_break_seconds(now=now),
    }

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def temperature_ocr(request):
    try:
        from market.services.temperature_ocr import extract_temperature_from_uploaded_file
    except ModuleNotFoundError:
        return Response(
            {
                "success": False,
                "message": "El servicio OCR no está instalado en este entorno.",
            },
            status=503,
        )

    image = request.FILES.get("image")

    if not image:
        return Response(
            {"success": False, "message": "No se recibió ninguna imagen."},
            status=400,
        )

    result = extract_temperature_from_uploaded_file(image)

    return Response(
        {
            "success": True,
            "data": result,
        }
    )

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def shift_me_today(request):
    shift = _get_open_shift(request.user)
    return Response(
        {
            "success": True,
            "data": _serialize_today_shift(shift),
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@transaction.atomic
def shift_start(request):
    open_shift = _get_open_shift(request.user)
    if open_shift:
        return Response(
            {
                "success": False,
                "message": "Ya tienes una jornada activa.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    latitude = request.data.get("latitude")
    longitude = request.data.get("longitude")

    market = _nearest_market(latitude, longitude) or _latest_market_for_user(
        request.user
    )

    shift = Shift.objects.create(
        user=request.user,
        market=market,
        started_at=timezone.now(),
        start_latitude=latitude if latitude is not None else None,
        start_longitude=longitude if longitude is not None else None,
    )

    return Response(
        {
            "success": True,
            "message": "Jornada iniciada correctamente.",
            "data": _serialize_today_shift(shift),
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@transaction.atomic
def break_start(request):
    shift = _get_open_shift(request.user)
    if not shift:
        return Response(
            {
                "success": False,
                "message": "No hay una jornada activa.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    if shift.on_break:
        return Response(
            {
                "success": False,
                "message": "Ya estás en descanso.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    shift.break_started_at = timezone.now()
    shift.save(update_fields=["break_started_at", "updated_at"])

    return Response(
        {
            "success": True,
            "message": "Descanso iniciado correctamente.",
            "data": _serialize_today_shift(shift),
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@transaction.atomic
def break_end(request):
    shift = _get_open_shift(request.user)
    if not shift:
        return Response(
            {
                "success": False,
                "message": "No hay una jornada activa.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not shift.on_break:
        return Response(
            {
                "success": False,
                "message": "No hay un descanso activo.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    shift.close_break(now=timezone.now())
    shift.save(update_fields=["break_started_at", "break_total_seconds", "updated_at"])

    return Response(
        {
            "success": True,
            "message": "Descanso finalizado correctamente.",
            "data": _serialize_today_shift(shift),
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@transaction.atomic
def shift_end(request):
    shift = _get_open_shift(request.user)
    if not shift:
        return Response(
            {
                "success": False,
                "message": "No hay una jornada activa.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    latitude = request.data.get("latitude")
    longitude = request.data.get("longitude")

    shift.end_latitude = latitude if latitude is not None else shift.end_latitude
    shift.end_longitude = longitude if longitude is not None else shift.end_longitude
    shift.close_shift(now=timezone.now())
    shift.save()

    return Response(
        {
            "success": True,
            "message": "Jornada finalizada correctamente.",
            "data": {
                "status": "OFF",
                "on_break": False,
                "market_name": shift.market.name if shift.market else None,
                "started_at": shift.started_at.isoformat(),
                "ended_at": shift.ended_at.isoformat() if shift.ended_at else None,
                "worked_seconds": shift.get_worked_seconds(now=shift.ended_at),
                "break_seconds": shift.get_break_seconds(now=shift.ended_at),
            },
        }
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def shift_me_calendar(request):
    month = request.query_params.get("month")
    if not month:
        return Response(
            {
                "success": False,
                "message": "Debes enviar el parámetro month con formato YYYY-MM.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        year, month_num = month.split("-")
        year = int(year)
        month_num = int(month_num)
    except Exception:
        return Response(
            {
                "success": False,
                "message": "Formato inválido. Usa YYYY-MM.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    shifts = Shift.objects.filter(
        user=request.user,
        started_at__year=year,
        started_at__month=month_num,
    ).order_by("started_at")

    days = []
    for shift in shifts:
        ended_or_now = shift.ended_at or timezone.now()
        break_seconds = shift.get_break_seconds(now=ended_or_now)
        worked_seconds = shift.get_worked_seconds(now=ended_or_now)

        days.append(
            {
                "date": shift.started_at.date().isoformat(),
                "workedSeconds": worked_seconds,
                "breakSeconds": break_seconds,
                "netSeconds": worked_seconds,
                "status": (
                    "BREAK" if shift.on_break else ("WORKING" if shift.is_open else "OFF")
                ),
                "marketName": shift.market.name if shift.market else None,
                "startedAt": shift.started_at.isoformat(),
                "endedAt": shift.ended_at.isoformat() if shift.ended_at else None,
            }
        )

    return Response(
        {
            "success": True,
            "data": {
                "month": month,
                "days": days,
            },
        }
    )
