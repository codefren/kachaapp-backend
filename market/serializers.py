from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from .models import Market
from django.utils import timezone


class MarketProximityTokenRefreshSerializer(TokenRefreshSerializer):
    """
    Serializer for refreshing JWT tokens.
    Requires latitude and longitude of the user. Only refreshes if the user is within 500 meters of any market.
    Fields:
      - refresh: str (JWT refresh token)
      - latitude: float (user's latitude)
      - longitude: float (user's longitude)
      - market_name: str (nombre del market más cercano)
      - login_time: str (timestamp del login/refresh)
    """
    latitude = serializers.FloatField(write_only=True, help_text="User's latitude in decimal degrees.")
    longitude = serializers.FloatField(write_only=True, help_text="User's longitude in decimal degrees.")
    market_name = serializers.SerializerMethodField()
    login_time = serializers.SerializerMethodField()

    def validate(self, attrs):
        latitude = attrs.get('latitude')
        longitude = attrs.get('longitude')
        market_qs = Market.objects.all()
        nearest_market = None
        for market in market_qs:
            if market.is_near(latitude, longitude, max_distance_meters=500):
                nearest_market = market
                break

        if not nearest_market:
            raise serializers.ValidationError('You are not near any market. Refresh denied.')

        self._market_name = nearest_market.name
        self._login_time = timezone.now()
        data = super().validate(attrs)
        # Include extra fields in response
        data['market_name'] = self._market_name
        data['login_time'] = self._login_time.strftime('%d/%m/%Y %H:%M')
        return data

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_market_name(self, obj):
        return getattr(self, '_market_name', None)

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_login_time(self, obj):
        if self._login_time is not None:
            return self._login_time.strftime('%d/%m/%Y %H:%M')
        return None


class MarketProximityTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Serializer for obtaining JWT tokens with market proximity validation.
    Requires username, password, latitude and longitude. Only issues tokens if user is within 500 meters of any market.
    Fields:
      - username: str
      - password: str
      - latitude: float (user's latitude)
      - longitude: float (user's longitude)
      - market_name: str (nombre del market más cercano)
      - login_time: str (timestamp del login)
    """
    latitude = serializers.FloatField(write_only=True, help_text="User's latitude in decimal degrees.")
    longitude = serializers.FloatField(write_only=True, help_text="User's longitude in decimal degrees.")
    market_name = serializers.SerializerMethodField()
    login_time = serializers.SerializerMethodField()

    def validate(self, attrs):
        latitude = attrs.get('latitude')
        longitude = attrs.get('longitude')
        market_qs = Market.objects.all()
        nearest_market = None
        for market in market_qs:
            if market.is_near(latitude, longitude, max_distance_meters=500):
                nearest_market = market
                break
        if not nearest_market:
            raise serializers.ValidationError('You are not near any market. Login denied.')
        # store for SerializerMethodFields
        self._market_name = nearest_market.name
        self._login_time = timezone.now()
        data = super().validate(attrs)
        # Include extra fields in response
        data['market_name'] = self._market_name
        data['login_time'] = self._login_time.strftime('%d/%m/%Y %H:%M')
        return data

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_market_name(self, obj):
        return getattr(self, '_market_name', None)

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_login_time(self, obj):
        if hasattr(self, '_login_time'):
            return self._login_time.strftime('%d/%m/%Y %H:%M')
        return None
