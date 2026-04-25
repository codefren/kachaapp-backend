import math
import logging
from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)

RANGE_METERS = 150
OUT_OF_RANGE_MINUTES = 15
MAX_NO_LOCATION_MINUTES = 30


def _haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))


@shared_task
def check_shifts_location():
    """Verifica ubicación de shifts activos y cierra los que llevan fuera de rango."""
    from .models import Shift
    from django.core.mail import send_mail

    now = timezone.now()
    open_shifts = Shift.objects.filter(
        ended_at__isnull=True,
        break_started_at__isnull=True,
    ).select_related('user', 'market', 'user__worker_profile')

    closed = 0
    for shift in open_shifts:
        # Sin ubicación reciente — no cerrar (app cerrada o sin GPS)
        if not shift.last_location_at:
            continue
        minutes_since_location = (now - shift.last_location_at).total_seconds() / 60
        if minutes_since_location > MAX_NO_LOCATION_MINUTES:
            continue

        # Sin tienda asignada — no verificar
        if not shift.market or not shift.market.latitude or not shift.market.longitude:
            continue

        distance = _haversine_distance(
            float(shift.last_latitude), float(shift.last_longitude),
            float(shift.market.latitude), float(shift.market.longitude)
        )
        in_range = distance <= RANGE_METERS

        if not in_range:
            if not shift.out_of_range_since:
                shift.out_of_range_since = now
                shift.save(update_fields=['out_of_range_since'])
            else:
                minutes_out = (now - shift.out_of_range_since).total_seconds() / 60
                if minutes_out >= OUT_OF_RANGE_MINUTES:
                    shift.close_shift(now=now)
                    shift.save()
                    closed += 1
                    logger.info(f"Shift {shift.id} cerrado por fuera de rango ({shift.user.username})")
                    try:
                        profile = shift.user.worker_profile
                        if profile.send_shift_limit_email and shift.user.email:
                            send_mail(
                                subject=f"Jornada cerrada - {shift.user.username}",
                                message=(
                                    f"Hola {shift.user.username},\n\n"
                                    f"Tu jornada ha sido cerrada automaticamente porque llevas mas de {OUT_OF_RANGE_MINUTES} minutos fuera del rango permitido de tu tienda.\n\n"
                                    f"Tienda: {shift.market.name}\n"
                                    f"Hora: {timezone.localtime(now).strftime('%d/%m/%Y %H:%M')}\n\n"
                                    f"Si fue un error contacta con tu responsable.\n\n"
                                    f"Saludos,\nKacha Digital BCN"
                                ),
                                from_email=None,
                                recipient_list=[shift.user.email],
                                fail_silently=True,
                            )
                    except Exception as e:
                        logger.error(f"Error enviando email cierre shift {shift.id}: {e}")
        else:
            if shift.out_of_range_since:
                shift.out_of_range_since = None
                shift.save(update_fields=['out_of_range_since'])

    # Verificar cierre por horario fin de jornada
    day_names = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
    local_now = timezone.localtime(now)
    current_day = day_names[local_now.weekday()]
    current_time = local_now.time()

    all_open_shifts = Shift.objects.filter(
        ended_at__isnull=True,
    ).select_related('user', 'market', 'user__worker_profile')

    for shift in all_open_shifts:
        try:
            profile = shift.user.worker_profile
            end_time = getattr(profile, f'{current_day}_end', None)
            if not end_time:
                continue
            if current_time >= end_time:
                shift.close_shift(now=now)
                shift.save()
                closed += 1
                logger.info(f"Shift {shift.id} cerrado por fin de horario ({shift.user.username})")
                if profile.send_shift_limit_email and shift.user.email:
                    from django.core.mail import send_mail
                    send_mail(
                        subject=f"Jornada cerrada por fin de horario - {shift.user.username}",
                        message=(
                            f"Hola {shift.user.username},\n\n"
                            f"Tu jornada ha sido cerrada automaticamente al llegar al fin de tu horario ({end_time.strftime('%H:%M')}).\n\n"
                            f"Tienda: {shift.market.name if shift.market else 'Sin tienda'}\n"
                            f"Hora: {local_now.strftime('%d/%m/%Y %H:%M')}\n\n"
                            f"Saludos,\nKacha Digital BCN"
                        ),
                        from_email=None,
                        recipient_list=[shift.user.email],
                        fail_silently=True,
                    )
        except Exception as e:
            logger.error(f"Error cerrando shift {shift.id} por horario: {e}")

    logger.info(f"check_shifts_location: {closed} shifts cerrados")
    return closed
