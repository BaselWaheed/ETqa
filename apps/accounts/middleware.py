import time

from django.conf import settings
from django.contrib.auth import logout

SESSION_STARTED_KEY = "etqa_auth_started_at"


class AbsoluteSessionTimeoutMiddleware:
    """Ends a session a fixed time after login, regardless of activity (idle timeout is the cookie age)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            started = request.session.get(SESSION_STARTED_KEY)
            limit = settings.SESSION_ABSOLUTE_HOURS * 3600
            if started is None:
                request.session[SESSION_STARTED_KEY] = time.time()
            elif time.time() - started > limit:
                logout(request)
        return self.get_response(request)
