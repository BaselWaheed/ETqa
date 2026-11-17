from django.contrib import admin, messages

from apps.audit.services import record

from . import services
from .models import Job, JobAttempt, WorkerHeartbeat


class AttemptInline(admin.TabularInline):
    model = JobAttempt
    extra = 0
    can_delete = False
    readonly_fields = ("attempt_no", "worker_id", "started_at", "finished_at", "outcome", "error")


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ("id", "kind", "queue", "status", "priority", "priority_boost", "attempts", "created_at", "heartbeat_at")
    list_filter = ("status", "queue", "kind")
    readonly_fields = [f.name for f in Job._meta.fields if f.name not in ("payload", "result", "progress")]
    exclude = ("payload", "result", "progress")  # may contain user text
    inlines = [AttemptInline]
    actions = ["requeue_jobs"]

    def has_module_permission(self, request):
        return request.user.has_perm("access.manage_any_job")

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm("access.manage_any_job")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description="Requeue failed or dead jobs")
    def requeue_jobs(self, request, queryset):
        n = 0
        for job in queryset:
            if services.requeue(job):
                n += 1
                record("jobs.requeued", request=request, obj=job)
        messages.info(request, f"{n} job(s) requeued.")


@admin.register(WorkerHeartbeat)
class WorkerAdmin(admin.ModelAdmin):
    list_display = ("worker_id", "queue", "last_seen", "current_job")

    def has_module_permission(self, request):
        return request.user.has_perm("access.manage_any_job")

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm("access.manage_any_job")
