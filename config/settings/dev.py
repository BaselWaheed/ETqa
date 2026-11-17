from .base import *  # noqa: F401,F403
from .base import LOG_DIR, LOGGING, SECRET_KEY, add_file_logging

DEBUG = True
if not SECRET_KEY:
    SECRET_KEY = "dev-only-insecure-key-do-not-use-elsewhere"  # noqa: S105
add_file_logging(LOGGING, LOG_DIR)

# Serve static files straight from static/ in development (no collectstatic needed).
WHITENOISE_USE_FINDERS = True
WHITENOISE_AUTOREFRESH = True
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
