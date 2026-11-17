from django import forms
from django.contrib.auth.forms import AuthenticationForm

from . import throttle
from apps.audit.services import client_ip


class ThrottledAuthenticationForm(AuthenticationForm):
    error_messages = {
        **AuthenticationForm.error_messages,
        "locked": "Too many failed sign-in attempts. Try again in %(minutes)s minutes or ask an administrator.",
    }

    def clean(self):
        from django.conf import settings

        username = self.cleaned_data.get("username") or ""
        ip = client_ip(self.request)
        if throttle.is_locked(username, ip):
            raise forms.ValidationError(self.error_messages["locked"], code="locked",
                                        params={"minutes": settings.LOGIN_LOCK_MINUTES})
        try:
            cleaned = super().clean()
        except forms.ValidationError:
            throttle.register_failure(username, ip)
            raise
        throttle.clear(username)
        return cleaned
