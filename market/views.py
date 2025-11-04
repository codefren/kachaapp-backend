from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .serializers import MarketProximityTokenObtainPairSerializer, MarketProximityTokenRefreshSerializer
from .models import LoginHistory, Market
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import ValidationError
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
        # Log completo de datos recibidos
        logger.info("[MarketProximity] === TOKEN REQUEST ===")
        logger.info("[MarketProximity] request.data: %s", dict(request.data))
        logger.info("[MarketProximity] request.user: %s", request.user)
        
        latitude = request.data.get('latitude')
        longitude = request.data.get('longitude')
        username = request.data.get('username')
        password_length = len(request.data.get('password', '')) if request.data.get('password') else 0
        
        logger.info("[MarketProximity] username=%s password_length=%s lat=%s lon=%s", 
                   username, password_length, latitude, longitude)
        logger.debug("[MarketProximity] Coordenadas recibidas (obtain) lat=%s lon=%s", latitude, longitude)

        try:
            serializer = self.get_serializer(data=request.data)
            logger.debug("[MarketProximity] Serializer initialized", extra={"has_data": bool(request.data)})

            if serializer.is_valid(raise_exception=True):
                market = getattr(serializer, '_market_name', None)
                user = getattr(serializer, "user", None) or request.user

                logger.info(
                    "[MarketProximity] Login attempt validated user=%s market=%s lat=%s lon=%s",
                    getattr(user, 'username', None) or getattr(user, 'id', None),
                    market,
                    latitude,
                    longitude,
                )

                self.log_login_history(user, market, latitude, longitude, LoginHistory.LOGIN)
                logger.debug("[MarketProximity] Login history recorded")

            response = super().post(request, *args, **kwargs)
            logger.info("[MarketProximity] Token issued successfully status=%s", response.status_code)
            return response
        except ValidationError as e:
            logger.warning(
                "[MarketProximity] Validation failed (obtain) lat=%s lon=%s errors=%s",
                latitude,
                longitude,
                getattr(e, 'detail', str(e)),
            )
            raise
        except Exception:
            logger.exception("[MarketProximity] Error processing token obtain POST")
            raise


class MarketProximityTokenRefreshView(MarketLoginHistoryMixin, TokenRefreshView):
    serializer_class = MarketProximityTokenRefreshSerializer

    def post(self, request, *args, **kwargs):
        latitude = request.data.get('latitude')
        longitude = request.data.get('longitude')
        # Debug explícito de coordenadas
        logger.debug("[MarketProximity] Coordenadas recibidas (refresh) lat=%s lon=%s", latitude, longitude)

        try:
            serializer = self.get_serializer(data=request.data)
            if serializer.is_valid(raise_exception=True):
                # Use stored attribute to avoid KeyError on serialization
                market = getattr(serializer, '_market_name', None)
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
                getattr(e, 'detail', str(e)),
            )
            raise
        except Exception:
            logger.exception("[MarketProximity] Error processing token refresh POST")
            raise
