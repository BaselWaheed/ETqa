from django.contrib.auth.models import Group
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .models import Collection
from .permissions import capability
from .serializers import CollectionSerializer, GrantSerializer


class CollectionListCreate(generics.ListCreateAPIView):
    """GET: collections the caller can read. POST: create (manage_collections only)."""

    serializer_class = CollectionSerializer

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated(), capability("manage_collections")()]
        return [IsAuthenticated()]

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["scope"] = services.scope_for(self.request.user)
        return ctx

    def get_queryset(self):
        scope = services.scope_for(self.request.user)
        return Collection.objects.filter(id__in=scope.readable, is_active=True)

    def perform_create(self, serializer):
        data = serializer.validated_data
        serializer.instance = services.create_collection(actor=self.request.user, request=self.request, **data)


class CollectionDetail(generics.RetrieveAPIView):
    """Unreadable collections return 404, so their existence is not disclosed."""

    serializer_class = CollectionSerializer

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["scope"] = services.scope_for(self.request.user)
        return ctx

    def get_queryset(self):
        scope = services.scope_for(self.request.user)
        return Collection.objects.filter(id__in=scope.readable, is_active=True)


class CollectionGrants(APIView):
    permission_classes = [IsAuthenticated, capability("manage_collections")]

    def get(self, request, pk: int):
        collection = get_object_or_404(Collection, pk=pk)
        grants = [{"group": g.group.name, "level": g.level} for g in collection.grants.select_related("group")]
        return Response(grants)

    def post(self, request, pk: int):
        collection = get_object_or_404(Collection, pk=pk)
        ser = GrantSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        services.set_grant(actor=request.user, request=request, collection=collection, **ser.validated_data)
        return Response(ser.data, status=status.HTTP_201_CREATED)


class CollectionGrantDelete(APIView):
    permission_classes = [IsAuthenticated, capability("manage_collections")]

    def delete(self, request, pk: int, group_name: str):
        collection = get_object_or_404(Collection, pk=pk)
        group = get_object_or_404(Group, name=group_name)
        if not services.remove_grant(actor=request.user, request=request, collection=collection, group=group):
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)
