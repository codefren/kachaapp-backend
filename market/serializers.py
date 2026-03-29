from django.utils import timezone
from rest_framework import serializers
from rest_framework_simplejwt.serializers import (
    TokenObtainPairSerializer,
    TokenRefreshSerializer,
)
from .models import Market


def get_nearest_market(latitude, longitude):
    if latitude is None or longitude is None:
        raise serializers.ValidationError("Latitude and longitude are required.")

    try:
        lat = float(latitude)
        lon = float(longitude)
    except:
        raise serializers.ValidationError("Invalid coordinates.")

    for market in Market.objects.all():
        try:
            if market.is_near(lat, lon, max_distance_meters=500):
                return market
        except:
            continue

    raise serializers.ValidationError("You are not near any market.")


class MarketProximityTokenObtainPairSerializer(TokenObtainPairSerializer):
    latitude = serializers.FloatField(write_only=True)
    longitude = serializers.FloatField(write_only=True)

    def validate(self, attrs):
        market = get_nearest_market(
            attrs.get("latitude"),
            attrs.get("longitude")
        )

        self._market = market
        self._login_time = timezone.now()

        data = super().validate(attrs)

        data["market_name"] = market.name
        data["login_time"] = self._login_time.strftime("%d/%m/%Y %H:%M")

        return data


class MarketProximityTokenRefreshSerializer(TokenRefreshSerializer):
    latitude = serializers.FloatField(write_only=True)
    longitude = serializers.FloatField(write_only=True)

    def validate(self, attrs):
        market = get_nearest_market(
            attrs.get("latitude"),
            attrs.get("longitude")
        )

        self._market = market
        self._login_time = timezone.now()

        data = super().validate(attrs)

        data["market_name"] = market.name
        data["login_time"] = self._login_time.strftime("%d/%m/%Y %H:%M")

        return data
