from django.contrib import admin

from apps.audit.services import record

from .models import Collection, CollectionGrant


class GrantInline(admin.TabularInline):
    model = CollectionGrant
    extra = 0


@admin.register(Collection)
class CollectionAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "business_unit", "is_active")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [GrantInline]

    def has_delete_permission(self, request, obj=None):
        return False  # deactivate instead; deletion would orphan documents later

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        record("access.collection_changed" if change else "access.collection_created", obj=obj, request=request,
               fields=sorted(form.changed_data))

    def save_formset(self, request, form, formset, change):
        super().save_formset(request, form, formset, change)
        for grant in formset.new_objects + [o for o, _ in formset.changed_objects]:
            record("access.grant_set", obj=grant.collection, request=request, group=grant.group.name, level=grant.level)
        for grant in formset.deleted_objects:
            record("access.grant_removed", obj=grant.collection, request=request, group=grant.group.name)
