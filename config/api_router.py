from django.conf import settings
from rest_framework.routers import DefaultRouter
from rest_framework.routers import SimpleRouter

from kachadigitalbcn.users.api.views import UserViewSet
from market.refrigerator_views import RefrigeratorViewSet

router = DefaultRouter() if settings.DEBUG else SimpleRouter()

router.register("users", UserViewSet)
router.register("refrigerators", RefrigeratorViewSet)


app_name = "api"
urlpatterns = router.urls
