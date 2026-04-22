from django.db import models
from django.utils import timezone
from rest_framework import permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from .models import WorkerProfile, MedicalLeave, VacationPeriod, LaborAbsence


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def worker_status(request):
    today = timezone.localdate()
    year_start = today.replace(month=1, day=1)

    try:
        profile = request.user.worker_profile
        vacation_remaining = profile.vacation_days_remaining
        vacation_total = profile.vacation_days_per_year
        vacation_used = profile.vacation_days_used
    except Exception:
        vacation_remaining = 0
        vacation_total = 30
        vacation_used = 0

    # Baja médica activa
    active_leave = MedicalLeave.objects.filter(
        user=request.user,
        start_date__lte=today,
    ).filter(
        models.Q(end_date__isnull=True) | models.Q(end_date__gte=today)
    ).first()

    # Días de baja médica este año
    medical_leaves_this_year = MedicalLeave.objects.filter(
        user=request.user,
        start_date__gte=year_start,
    )
    medical_days_this_year = 0
    for leave in medical_leaves_this_year:
        end = leave.end_date or today
        medical_days_this_year += (end - leave.start_date).days + 1

    # Ausencias laborales este año
    absences_this_year = LaborAbsence.objects.filter(
        user=request.user,
        date__gte=year_start,
    ).count()

    # Próximas vacaciones aprobadas
    next_vacation = VacationPeriod.objects.filter(
        user=request.user,
        end_date__gte=today,
        approved=True,
    ).order_by('start_date').first()

    # Días trabajados este mes
    from market.models import Shift
    month_start = today.replace(day=1)
    days_worked_this_month = Shift.objects.filter(
        user=request.user,
        started_at__date__gte=month_start,
        ended_at__isnull=False,
    ).values('started_at__date').distinct().count()

    return Response({
        "success": True,
        "data": {
            "vacation_days_total": vacation_total,
            "vacation_days_used": vacation_used,
            "vacation_days_remaining": vacation_remaining,
            "on_medical_leave": active_leave is not None,
            "medical_leave_since": active_leave.start_date.isoformat() if active_leave else None,
            "medical_days_this_year": medical_days_this_year,
            "absences_this_year": absences_this_year,
            "next_vacation_start": next_vacation.start_date.isoformat() if next_vacation else None,
            "next_vacation_end": next_vacation.end_date.isoformat() if next_vacation else None,
            "days_worked_this_month": days_worked_this_month,
        }
    })
