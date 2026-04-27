from django.urls import path

from .views import user_detail_view
from .views import user_redirect_view
from .views import user_update_view

app_name = "users"
from .views import user_me
urlpatterns = [
    path("~redirect/", view=user_redirect_view, name="redirect"),
    path("~update/", view=user_update_view, name="update"),
    path("<str:username>/", view=user_detail_view, name="detail"),
    path("me/", view=user_me, name="me"),
]
