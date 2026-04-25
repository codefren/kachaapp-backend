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

    # Verificar horario del trabajador
    try:
        profile = request.user.worker_profile
        local_now = timezone.localtime(timezone.now())
        day_names = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        day = day_names[local_now.weekday()]
        start = getattr(profile, f'{day}_start', None)
        end = getattr(profile, f'{day}_end', None)
        if start or end:
            current_time = local_now.time()
            if end and current_time >= end:
                return Response({
                    "success": False,
                    "message": f"Tu jornada laboral ha terminado. Horario de hoy hasta las {end.strftime('%H:%M')}.",
                }, status=status.HTTP_400_BAD_REQUEST)
            if start:
                from datetime import timedelta
                tolerance = getattr(profile, 'checkin_tolerance_minutes', 15)
                start_dt = local_now.replace(hour=start.hour, minute=start.minute, second=0)
                window_start = (start_dt - timedelta(minutes=tolerance)).time()
                if current_time < window_start:
                    return Response({
                        "success": False,
                        "message": f"Tu jornada no empieza hasta las {start.strftime('%H:%M')}.",
                    }, status=status.HTTP_400_BAD_REQUEST)
    except Exception:
        pass
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

    # Verificar horario del trabajador
    try:
        profile = request.user.worker_profile
        local_now = timezone.localtime(timezone.now())
        day_names = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        day = day_names[local_now.weekday()]
        end = getattr(profile, f'{day}_end', None)
        if end and local_now.time() >= end:
            return Response({
                "success": False,
                "message": f"Tu jornada laboral ha terminado. Horario de hoy hasta las {end.strftime('%H:%M')}.",
            }, status=status.HTTP_400_BAD_REQUEST)
    except Exception:
        pass
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

    # Enviar email si el usuario tiene configurado el envío
    try:
        profile = request.user.worker_profile
        if profile.send_shift_limit_email and request.user.email:
            worked = shift.get_worked_seconds(now=shift.ended_at)
            breaks = shift.get_break_seconds(now=shift.ended_at)
            h_worked = worked // 3600
            m_worked = (worked % 3600) // 60
            h_break = breaks // 3600
            m_break = (breaks % 3600) // 60
            from django.core.mail import send_mail
            send_mail(
                subject=f"Jornada finalizada - {request.user.username}",
                message=(
                    f"Hola {request.user.username},\n\n"
                    f"Tu jornada ha finalizado.\n\n"
                    f"Tienda: {shift.market.name if shift.market else 'Sin tienda'}\n"
                    f"Inicio: {timezone.localtime(shift.started_at).strftime('%d/%m/%Y %H:%M')}\n"
                    f"Fin: {timezone.localtime(shift.ended_at).strftime('%d/%m/%Y %H:%M')}\n"
                    f"Trabajado: {h_worked:02d}h {m_worked:02d}min\n"
                    f"Descanso: {h_break:02d}h {m_break:02d}min\n\n"
                    f"Saludos,\nKacha Digital BCN"
                ),
                from_email=None,
                recipient_list=[request.user.email],
                fail_silently=True,
            )
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f'Email error shift_end: {e}')

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


import math

def _haversine_distance(lat1, lon1, lat2, lon2):
    """Distancia en metros entre dos coordenadas."""
    R = 6371000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

RANGE_METERS = 150
OUT_OF_RANGE_MINUTES = 15


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def update_location(request):
    """Actualiza la ubicación del trabajador en su shift activo."""
    shift = _get_open_shift(request.user)
    if not shift:
        return Response({"success": False, "message": "No hay jornada activa."}, status=400)

    latitude = request.data.get("latitude")
    longitude = request.data.get("longitude")
    if latitude is None or longitude is None:
        return Response({"success": False, "message": "Faltan coordenadas."}, status=400)

    now = timezone.now()
    shift.last_latitude = latitude
    shift.last_longitude = longitude
    shift.last_location_at = now

    # Verificar distancia a la tienda solo si está trabajando (no en descanso)
    in_range = True
    if not shift.on_break and shift.market and shift.market.latitude and shift.market.longitude:
        distance = _haversine_distance(
            float(latitude), float(longitude),
            float(shift.market.latitude), float(shift.market.longitude)
        )
        in_range = distance <= RANGE_METERS

        if not in_range:
            if not shift.out_of_range_since:
                shift.out_of_range_since = now
            else:
                minutes_out = (now - shift.out_of_range_since).total_seconds() / 60
                if minutes_out >= OUT_OF_RANGE_MINUTES:
                    # Cerrar jornada automáticamente
                    shift.close_shift(now=now)
                    shift.save()
                    # Enviar email
                    try:
                        profile = request.user.worker_profile
                        if profile.send_shift_limit_email and request.user.email:
                            from django.core.mail import send_mail
                            send_mail(
                                subject=f"Jornada cerrada automaticamente - {request.user.username}",
                                message=(
                                    f"Hola {request.user.username},\n\n"
                                    f"Tu jornada ha sido cerrada automaticamente porque llevas mas de {OUT_OF_RANGE_MINUTES} minutos fuera del rango permitido de tu tienda.\n\n"
                                    f"Tienda: {shift.market.name if shift.market else 'Sin tienda'}\n"
                                    f"Hora de cierre: {timezone.localtime(now).strftime('%d/%m/%Y %H:%M')}\n\n"
                                    f"Si fue un error contacta con tu responsable.\n\n"
                                    f"Saludos,\nKacha Digital BCN"
                                ),
                                from_email=None,
                                recipient_list=[request.user.email],
                                fail_silently=True,
                            )
                    except Exception:
                        pass
                    return Response({
                        "success": True,
                        "auto_closed": True,
                        "message": "Jornada cerrada automaticamente por estar fuera del rango permitido.",
                        "data": _serialize_today_shift(shift),
                    })
        else:
            shift.out_of_range_since = None

    shift.save(update_fields=['last_latitude', 'last_longitude', 'last_location_at', 'out_of_range_since'])

    return Response({
        "success": True,
        "auto_closed": False,
        "in_range": in_range,
        "data": _serialize_today_shift(shift),
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def check_range_for_break_end(request):
    """Verifica si el trabajador está en rango para reanudar trabajo."""
    shift = _get_open_shift(request.user)
    if not shift:
        return Response({"success": False, "message": "No hay jornada activa."}, status=400)

    latitude = request.data.get("latitude")
    longitude = request.data.get("longitude")

    if not shift.market or not shift.market.latitude or not shift.market.longitude:
        return Response({"success": True, "in_range": True})

    if latitude is None or longitude is None:
        return Response({"success": False, "message": "Faltan coordenadas."}, status=400)

    distance = _haversine_distance(
        float(latitude), float(longitude),
        float(shift.market.latitude), float(shift.market.longitude)
    )
    in_range = distance <= RANGE_METERS

    return Response({
        "success": True,
        "in_range": in_range,
        "message": "" if in_range else "No estas en el rango permitido para reanudar tu jornada.",
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def auto_check(request):
    """Verifica ubicación y gestiona inicio/cierre automático de jornada."""
    latitude = request.data.get("latitude")
    longitude = request.data.get("longitude")
    if latitude is None or longitude is None:
        return Response({"success": False, "message": "Faltan coordenadas."}, status=400)

    now = timezone.now()
    local_now = timezone.localtime(now)
    shift = _get_open_shift(request.user)

    # Obtener perfil del trabajador
    try:
        profile = request.user.worker_profile
        auto_checkin = profile.auto_checkin_enabled
        tolerance = profile.checkin_tolerance_minutes
    except Exception:
        auto_checkin = False
        tolerance = 15

    # Verificar si está dentro del horario permitido
    def is_within_schedule():
        if not auto_checkin:
            return False
        day_names = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        day = day_names[local_now.weekday()]
        start = getattr(profile, f'{day}_start', None)
        end = getattr(profile, f'{day}_end', None)
        if not start:
            return False
        from datetime import timedelta
        start_dt = local_now.replace(hour=start.hour, minute=start.minute, second=0)
        window_start = start_dt - timedelta(minutes=tolerance)
        # Verificar que no ha pasado la hora de fin
        if end:
            end_dt = local_now.replace(hour=end.hour, minute=end.minute, second=0)
            if local_now >= end_dt:
                return False
        return local_now >= window_start

    # Si no hay jornada activa
    if not shift:
        if not is_within_schedule():
            return Response({
                "success": True,
                "action": "none",
                "message": "Fuera de horario de fichaje.",
                "data": _serialize_today_shift(None),
            })
        # Verificar si está cerca de una tienda
        nearest = _nearest_market(latitude, longitude)
        if not nearest:
            return Response({
                "success": True,
                "action": "none",
                "message": "No hay tienda cercana.",
                "data": _serialize_today_shift(None),
            })
        # Iniciar jornada automáticamente
        shift = Shift.objects.create(
            user=request.user,
            market=nearest,
            started_at=now,
            start_latitude=latitude,
            start_longitude=longitude,
            last_latitude=latitude,
            last_longitude=longitude,
            last_location_at=now,
        )
        return Response({
            "success": True,
            "action": "started",
            "message": f"Jornada iniciada automáticamente en {nearest.name}.",
            "data": _serialize_today_shift(shift),
        })

    # Si hay jornada activa — actualizar ubicación
    shift.last_latitude = latitude
    shift.last_longitude = longitude
    shift.last_location_at = now

    # Solo verificar rango si está trabajando (no en descanso)
    if not shift.on_break and shift.market and shift.market.latitude and shift.market.longitude:
        distance = _haversine_distance(
            float(latitude), float(longitude),
            float(shift.market.latitude), float(shift.market.longitude)
        )
        in_range = distance <= RANGE_METERS

        if not in_range:
            if not shift.out_of_range_since:
                shift.out_of_range_since = now
            else:
                minutes_out = (now - shift.out_of_range_since).total_seconds() / 60
                if minutes_out >= OUT_OF_RANGE_MINUTES:
                    shift.close_shift(now=now)
                    shift.save()
                    try:
                        if profile.send_shift_limit_email and request.user.email:
                            from django.core.mail import send_mail
                            send_mail(
                                subject=f"Jornada cerrada - {request.user.username}",
                                message=(
                                    f"Hola {request.user.username},\n\n"
                                    f"Tu jornada ha sido cerrada automaticamente porque llevas mas de {OUT_OF_RANGE_MINUTES} minutos fuera del rango permitido.\n\n"
                                    f"Tienda: {shift.market.name}\n"
                                    f"Hora: {local_now.strftime('%d/%m/%Y %H:%M')}\n\n"
                                    f"Saludos,\nKacha Digital BCN"
                                ),
                                from_email=None,
                                recipient_list=[request.user.email],
                                fail_silently=True,
                            )
                    except Exception:
                        pass
                    return Response({
                        "success": True,
                        "action": "closed",
                        "message": "Jornada cerrada automáticamente por estar fuera del rango permitido.",
                        "data": _serialize_today_shift(shift),
                    })
        else:
            shift.out_of_range_since = None

    shift.save(update_fields=['last_latitude', 'last_longitude', 'last_location_at', 'out_of_range_since'])

    return Response({
        "success": True,
        "action": "updated",
        "data": _serialize_today_shift(shift),
    })
