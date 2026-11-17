from rest_framework import serializers

from .models import User


class MeSerializer(serializers.ModelSerializer):
    roles = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "preferred_language", "roles"]
        read_only_fields = ["id", "username", "roles"]

    def get_roles(self, obj) -> list[str]:
        return sorted(obj.groups.values_list("name", flat=True))
