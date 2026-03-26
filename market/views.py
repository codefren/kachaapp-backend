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
        logger.info("[MarketProximity] === TOKEN REQUEST ===")
        logger.info("[MarketProximity] request.data: %s", request.data)
        logger.info("[MarketProximity] request.user: %s", request.user)

        latitude = request.data.get("latitude")
        longitude = request.data.get("longitude")
        username = request.data.get("username")
        password_length = len(request.data.get("password", "")) if request.data.get("password") else 0

        logger.info(
            "[MarketProximity] username=%s password_length=%s lat=%s lon=%s",
            username,
            password_length,
            latitude,
            longitude,
        )

        try:
            serializer = self.get_serializer(data=request.data)

            if serializer.is_valid(raise_exception=True):
                market = getattr(serializer, "_market", None)
                user = getattr(serializer, "user", None) or request.user

                logger.info(
                    "[MarketProximity] Login validated user=%s market=%s lat=%s lon=%s",
                    getattr(user, "username", None) or getattr(user, "id", None),
                    getattr(market, "name", None),
                    latitude,
                    longitude,
                )

                self.log_login_history(user, market, latitude, longitude, LoginHistory.LOGIN)

            response = super().post(request, *args, **kwargs)
            logger.info("[MarketProximity] Token issued successfully status=%s", response.status_code)
            return response

        except ValidationError as e:
            logger.warning(
                "[MarketProximity] Validation failed (obtain) lat=%s lon=%s errors=%s",
                latitude,
                longitude,
                getattr(e, "detail", str(e)),
            )
            raise
        except Exception:
            logger.exception("[MarketProximity] Error processing token obtain POST")
            raise


class MarketProximityTokenRefreshView(MarketLoginHistoryMixin, TokenRefreshView):
    serializer_class = MarketProximityTokenRefreshSerializer

    def post(self, request, *args, **kwargs):
        latitude = request.data.get("latitude")
        longitude = request.data.get("longitude")

        logger.debug(
            "[MarketProximity] Coordenadas recibidas (refresh) lat=%s lon=%s",
            latitude,
            longitude,
        )

        try:
            serializer = self.get_serializer(data=request.data)

            if serializer.is_valid(raise_exception=True):
                market = getattr(serializer, "_market", None)
                user = getattr(serializer, "user", None) or request.user
                self.log_login_history(user, market, latitude, longitude, LoginHistory.REFRESH)

            response = super().post(request, *args, **kwargs)
            logger.info("[MarketProximity] Token refreshed successfully status=%s", response.status_code)
            return response

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

    market = _nearest_market(latitude, longitude) or _latest_market_for_user(request.user)

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
                "status": "BREAK" if shift.on_break else ("WORKING" if shift.is_open else "OFF"),
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
