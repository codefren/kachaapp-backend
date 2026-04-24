from django.urls import path
from . import views

app_name = "market"

urlpatterns = [
    path("shifts/me/today/", views.shift_me_today, name="shift_me_today"),
    path("shifts/me/start/", views.shift_start, name="shift_start"),
    path("shifts/me/end/", views.shift_end, name="shift_end"),
    path("shifts/me/break/start/", views.break_start, name="break_start"),
    path("shifts/me/break/end/", views.break_end, name="break_end"),
    path("shifts/me/calendar/", views.shift_me_calendar, name="shift_me_calendar"),
    path("shifts/me/location/", views.update_location, name="update_location"),
    path("shifts/me/check-range/", views.check_range_for_break_end, name="check_range"),
    path("shifts/me/auto-check/", views.auto_check, name="auto_check"),
    path("temperatures/ocr/", views.temperature_ocr, name="temperature_ocr"),
]
