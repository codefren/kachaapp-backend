from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer
from rest_framework import serializers
from .models import Market


class MarketProximityTokenRefreshSerializer(TokenRefreshSerializer):
    """
    Serializer for refreshing JWT tokens.
    Requires latitude and longitude of the user. Only refreshes if the user is within 500 meters of any market.
    Fields:
      - refresh: str (JWT refresh token)
      - latitude: float (user's latitude)
      - longitude: float (user's longitude)
    """
    latitude = serializers.FloatField(write_only=True, help_text="User's latitude in decimal degrees.")
    longitude = serializers.FloatField(write_only=True, help_text="User's longitude in decimal degrees.")

    def validate(self, attrs):
        latitude = attrs.get('latitude')
        longitude = attrs.get('longitude')
        market_qs = Market.objects.all()
        found = False
        for market in market_qs:
            if market.is_near(latitude, longitude, max_distance_meters=500):
                found = True
                break
        if not found:
            raise serializers.ValidationError('You are not near any market. Refresh denied.')
        return super().validate(attrs)


class MarketProximityTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Serializer for obtaining JWT tokens with market proximity validation.
    Requires username, password, latitude and longitude. Only issues tokens if user is within 500 meters of any market.
    Fields:
      - username: str
      - password: str
      - latitude: float (user's latitude)
      - longitude: float (user's longitude)
    """
    latitude = serializers.FloatField(write_only=True, help_text="User's latitude in decimal degrees.")
    longitude = serializers.FloatField(write_only=True, help_text="User's longitude in decimal degrees.")

    def validate(self, attrs):
        # Validar usuario y password normalmente
        data = super().validate(attrs)
        latitude = attrs.get('latitude')
        longitude = attrs.get('longitude')
        # Buscar markets cercanos
        market_qs = Market.objects.all()
        found = False
        for market in market_qs:
            if market.is_near(latitude, longitude, max_distance_meters=500):
                found = True
                break
        if not found:
            raise serializers.ValidationError('You are not near any market. Login denied.')
        return data
