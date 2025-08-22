from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .serializers import MarketProximityTokenObtainPairSerializer, MarketProximityTokenRefreshSerializer
from .models import LoginHistory, Market
from django.shortcuts import get_object_or_404
import logging

logger = logging.getLogger(__name__)

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
        client_ip = request.META.get('REMOTE_ADDR')
        logger.info("[MarketProximity] POST received for token obtain", extra={"client_ip": client_ip})

        try:
            serializer = self.get_serializer(data=request.data)
            logger.debug("[MarketProximity] Serializer initialized", extra={"has_data": bool(request.data)})

            if serializer.is_valid(raise_exception=True):
                # Use stored attribute to avoid KeyError on serialization
                market = getattr(serializer, '_market_name', None)
                latitude = request.data.get('latitude')
                longitude = request.data.get('longitude')
                user = getattr(serializer, "user", None) or request.user

                # Debug explícito de coordenadas
                logger.debug(
                    "[MarketProximity] Coordenadas recibidas (obtain)",
                    extra={"lat": latitude, "lon": longitude},
                )

                logger.info(
                    "[MarketProximity] Login attempt validated",
                    extra={
                        "user": getattr(user, 'username', None) or getattr(user, 'id', None),
                        "market": market,
                        "lat": latitude,
                        "lon": longitude,
                        "client_ip": client_ip,
                    },
                )

                self.log_login_history(user, market, latitude, longitude, LoginHistory.LOGIN)
                logger.debug("[MarketProximity] Login history recorded")

            response = super().post(request, *args, **kwargs)
            logger.info("[MarketProximity] Token issued successfully", extra={"status_code": response.status_code})
            return response
        except Exception:
            # Will include stack trace
            logger.exception("[MarketProximity] Error processing token obtain POST")
            raise


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
            # Debug explícito de coordenadas
            logger.debug(
                "[MarketProximity] Coordenadas recibidas (refresh)",
                extra={"lat": latitude, "lon": longitude},
            )
            self.log_login_history(user, market, latitude, longitude, LoginHistory.REFRESH)
        return super().post(request, *args, **kwargs)
