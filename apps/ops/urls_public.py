from django.urls import path

from .views import public_health

urlpatterns = [path("", public_health, name="health")]
