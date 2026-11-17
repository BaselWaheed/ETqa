from django.urls import path

from . import api

urlpatterns = [
    path("collections/", api.CollectionListCreate.as_view(), name="api-collections"),
    path("collections/<int:pk>/", api.CollectionDetail.as_view(), name="api-collection"),
    path("collections/<int:pk>/grants/", api.CollectionGrants.as_view(), name="api-collection-grants"),
    path("collections/<int:pk>/grants/<str:group_name>/", api.CollectionGrantDelete.as_view(), name="api-collection-grant"),
]
