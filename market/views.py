from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .serializers import MarketProximityTokenObtainPairSerializer, MarketProximityTokenRefreshSerializer
from .models import LoginHistory, Market
from django.shortcuts import get_object_or_404


class MarketLoginHistoryMixin:
    def log_login_history(self, user, market, latitude, longitude, event_type):
        market = get_object_or_404(Market, name=market)
        if user and getattr(user, "is_authenticated", False) and market:
            LoginHistory.objects.create(
                user=user,
                market=market,
                latitude=latitude,
                longitude=longitude,
                event_type=event_type
            )


class MarketProximityTokenObtainPairView(MarketLoginHistoryMixin, TokenObtainPairView):
    serializer_class = MarketProximityTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid(raise_exception=True):
            # Use stored attribute to avoid KeyError on serialization
            market = getattr(serializer, '_market_name', None)
            latitude = request.data.get('latitude')
            longitude = request.data.get('longitude')
            user = getattr(serializer, "user", None) or request.user
            self.log_login_history(user, market, latitude, longitude, LoginHistory.LOGIN)
        return super().post(request, *args, **kwargs)


class MarketProximityTokenRefreshView(MarketLoginHistoryMixin, TokenRefreshView):
    serializer_class = MarketProximityTokenRefreshSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid(raise_exception=True):
            # Use stored attribute to avoid KeyError on serialization
            market = getattr(serializer, '_market_name', None)
            latitude = request.data.get('latitude')
            longitude = request.data.get('longitude')
            user = getattr(serializer, "user", None) or request.user
            self.log_login_history(user, market, latitude, longitude, LoginHistory.REFRESH)
        return super().post(request, *args, **kwargs)
