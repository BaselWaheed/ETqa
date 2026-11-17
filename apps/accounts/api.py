from rest_framework import generics

from .serializers import MeSerializer


class MeView(generics.RetrieveUpdateAPIView):
    """The signed-in user's profile; only preferred_language and names are editable."""

    serializer_class = MeSerializer
    http_method_names = ["get", "patch"]

    def get_object(self):
        return self.request.user
