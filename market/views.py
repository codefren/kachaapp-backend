from django.shortcuts import render

from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .serializers import MarketProximityTokenObtainPairSerializer, MarketProximityTokenRefreshSerializer

class MarketProximityTokenObtainPairView(TokenObtainPairView):
    serializer_class = MarketProximityTokenObtainPairSerializer

class MarketProximityTokenRefreshView(TokenRefreshView):
    serializer_class = MarketProximityTokenRefreshSerializer
