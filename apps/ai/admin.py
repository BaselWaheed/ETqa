from django.contrib import admin

from apps.audit.services import record

from .models import AIExecution, AIModel, PromptTemplate, TaskRoute


class _ConfigAdmin(admin.ModelAdmin):
    def _ok(self, request):
        return request.user.has_perm("access.configure_models")

    def has_module_permission(self, request):
        return self._ok(request)

    def has_view_permission(self, request, obj=None):
        return self._ok(request)

    def has_change_permission(self, request, obj=None):
        return self._ok(request)

    def has_add_permission(self, request):
        return self._ok(request)

    def has_delete_permission(self, request, obj=None):
        return self._ok(request)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        record(f"ai.{obj._meta.model_name}_saved", request=request, obj=obj, fields=sorted(form.changed_data))


@admin.register(AIModel)
class AIModelAdmin(_ConfigAdmin):
    list_display = ("key", "runtime_name", "kind", "license", "context_limit", "keep_alive", "enabled")


@admin.register(TaskRoute)
class TaskRouteAdmin(_ConfigAdmin):
    list_display = ("task", "priority", "model", "max_tokens", "temperature", "no_downgrade")


@admin.register(PromptTemplate)
class PromptAdmin(_ConfigAdmin):
    list_display = ("task", "version", "is_active", "created_at")


@admin.register(AIExecution)
class ExecutionAdmin(admin.ModelAdmin):
    list_display = ("created_at", "task", "model_key", "prompt_tokens", "output_tokens", "first_token_ms", "total_ms", "outcome", "error_code")
    list_filter = ("task", "outcome", "model_key")

    def has_module_permission(self, request):
        return request.user.has_perm("access.view_audit")

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm("access.view_audit")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
