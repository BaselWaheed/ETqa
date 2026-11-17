from django.contrib import admin

from .models import TCTemplate


@admin.register(TCTemplate)
class TemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "is_default")

    def has_module_permission(self, request):
        return request.user.has_perm("access.configure_models")

    has_view_permission = has_change_permission = has_add_permission = \
        lambda self, request, obj=None: request.user.has_perm("access.configure_models")
