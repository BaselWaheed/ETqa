from django.contrib.auth import logout
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect
from django.views.decorators.http import require_POST

from .forms import ThrottledAuthenticationForm


class ThrottledLoginView(LoginView):
    form_class = ThrottledAuthenticationForm
    template_name = "registration/login.html"
    redirect_authenticated_user = True


@require_POST
def logout_view(request):
    logout(request)
    return redirect("login")
