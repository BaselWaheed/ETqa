from django.contrib import admin

from .models import Feedback


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ("created_at", "user", "rating", "message")
    list_filter = ("rating",)

    def has_module_permission(self, request):
        return request.user.has_perm("access.review_knowledge")

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm("access.review_knowledge")
