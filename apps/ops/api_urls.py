from django.urls import path

from .views import AdminHealth

urlpatterns = [path("health/", AdminHealth.as_view(), name="api-ops-health")]
