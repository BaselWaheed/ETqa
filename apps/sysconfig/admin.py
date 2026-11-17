import json

from django import forms
from django.contrib import admin

from apps.audit.services import record

from . import services
from .defaults import DEFAULTS
from .models import SystemSetting


class SettingForm(forms.ModelForm):
    key = forms.ChoiceField(choices=sorted((k, k) for k in DEFAULTS))

    class Meta:
        model = SystemSetting
        fields = ["key", "value"]

    def clean(self):
        data = super().clean()
        if "key" in data and "value" in data:
            services.validate(data["key"], data["value"])
        return data


@admin.register(SystemSetting)
class SystemSettingAdmin(admin.ModelAdmin):
    form = SettingForm
    list_display = ("key", "value_display", "default_display", "updated_by", "updated_at")
    search_fields = ("key",)

    @admin.display(description="value")
    def value_display(self, obj):
        return json.dumps(obj.value, ensure_ascii=False)[:80]

    @admin.display(description="default")
    def default_display(self, obj):
        return json.dumps(DEFAULTS.get(obj.key, ("?",))[0], ensure_ascii=False)[:80]

    def has_module_permission(self, request):
        return request.user.has_perm("access.configure_models")

    has_view_permission = has_change_permission = has_add_permission = has_delete_permission = \
        lambda self, request, obj=None: request.user.has_perm("access.configure_models")

    def save_model(self, request, obj, form, change):
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)
        services.invalidate()
        record("settings.changed", request=request, object_type="setting", object_id=obj.key)

    def delete_model(self, request, obj):
        record("settings.reset", request=request, object_type="setting", object_id=obj.key)
        super().delete_model(request, obj)
        services.invalidate()
