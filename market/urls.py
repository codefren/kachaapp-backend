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
]
