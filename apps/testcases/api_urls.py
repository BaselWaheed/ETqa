from django.urls import path

from . import api

urlpatterns = [
    path("testcases/sets/", api.Sets.as_view(), name="api-tc-sets"),
    path("testcases/sets/<int:pk>/", api.SetDetail.as_view(), name="api-tc-set"),
    path("testcases/sets/<int:pk>/export.xlsx", api.Export.as_view(), name="api-tc-export"),
    path("testcases/templates/", api.Templates.as_view(), name="api-tc-templates"),
]
