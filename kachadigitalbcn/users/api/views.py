from rest_framework import status
from rest_framework.decorators import action
from rest_framework.mixins import ListModelMixin
from rest_framework.mixins import RetrieveModelMixin
from rest_framework.mixins import UpdateModelMixin
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet
from rest_framework.parsers import MultiPartParser, FormParser

from kachadigitalbcn.users.models import User
from .serializers import UserSerializer


class UserViewSet(
    RetrieveModelMixin,
    ListModelMixin,
    UpdateModelMixin,
    GenericViewSet
):
    serializer_class = UserSerializer
    queryset = User.objects.all()
    lookup_field = "username"
    permission_classes = [IsAuthenticated]

    def get_queryset(self, *args, **kwargs):
        return self.queryset.filter(id=self.request.user.id)

    @action(detail=False, methods=["get"])
    def me(self, request):
        serializer = UserSerializer(
            request.user,
            context={"request": request}
        )
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(
        detail=False,
        methods=["post"],
        url_path="upload-photo",
        parser_classes=[MultiPartParser, FormParser],
    )
    def upload_photo(self, request):
        photo = request.FILES.get("photo")

        if not photo:
            return Response(
                {"detail": "No se ha enviado ninguna foto."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = request.user
        user.photo = photo
        user.save(update_fields=["photo"])

        serializer = UserSerializer(
            user,
            context={"request": request}
        )

        return Response(serializer.data, status=status.HTTP_200_OK)
