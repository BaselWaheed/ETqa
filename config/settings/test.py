from .base import *  # noqa: F401,F403

DEBUG = False
SECRET_KEY = "test-only-key"  # noqa: S105
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # speed only; never outside tests
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
WHITENOISE_USE_FINDERS = True  # tests do not run collectstatic
