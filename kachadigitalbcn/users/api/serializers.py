from rest_framework import serializers

from kachadigitalbcn.users.models import User


class UserSerializer(serializers.ModelSerializer[User]):
    photo = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "username", "name", "role", "photo", "url"]

        extra_kwargs = {
            "url": {"view_name": "api:user-detail", "lookup_field": "username"},
        }

    def get_photo(self, obj):
        request = self.context.get("request")

        if not obj.photo:
            return None

        if request:
            return request.build_absolute_uri(obj.photo.url)

        return obj.photo.url
