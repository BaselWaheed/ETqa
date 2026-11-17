from django.urls import path

from . import api

urlpatterns = [
    path("jobs/<int:pk>/", api.JobStatus.as_view(), name="api-job"),
    path("jobs/<int:pk>/cancel/", api.JobCancel.as_view(), name="api-job-cancel"),
    path("jobs/<int:pk>/requeue/", api.JobRequeue.as_view(), name="api-job-requeue"),
]
