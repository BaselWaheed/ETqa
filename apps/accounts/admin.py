from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class ETqaUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("ETqa", {"fields": ("preferred_language",)}),)
