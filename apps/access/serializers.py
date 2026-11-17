from django.contrib.auth.models import Group
from rest_framework import serializers

from .models import Collection, CollectionGrant


class CollectionSerializer(serializers.ModelSerializer):
    access = serializers.SerializerMethodField()

    class Meta:
        model = Collection
        fields = ["id", "name", "slug", "business_unit", "description", "is_active", "access"]
        read_only_fields = ["id", "is_active", "access"]

    def get_access(self, obj) -> str:
        scope = self.context["scope"]
        request = self.context.get("request")
        if scope.can_manage(obj.id) or (request and request.user.has_perm("access.manage_collections")):
            return "manage"
        return "read"


class GrantSerializer(serializers.Serializer):
    group = serializers.SlugRelatedField(slug_field="name", queryset=Group.objects.all())
    level = serializers.ChoiceField(choices=CollectionGrant.Level.choices)
