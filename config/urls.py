from django.contrib import admin
from django.urls import include, path

from apps.accounts import views as account_views

urlpatterns = [
    path("health", include("apps.ops.urls_public")),
    path("accounts/login/", account_views.ThrottledLoginView.as_view(), name="login"),
    path("accounts/logout/", account_views.logout_view, name="logout"),
    path("admin/", admin.site.urls),
    path("api/v1/", include("apps.accounts.api_urls")),
    path("api/v1/", include("apps.access.api_urls")),
    path("api/v1/ops/", include("apps.ops.api_urls")),
    path("api/v1/", include("apps.jobs.api_urls")),
    path("api/v1/", include("apps.documents.api_urls")),
    path("api/v1/", include("apps.chat.api_urls")),
    path("api/v1/", include("apps.testcases.api_urls")),
    path("", include("apps.ui.urls")),
]
