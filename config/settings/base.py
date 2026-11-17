"""Shared settings. Environment-specific values come from environment variables or .env (never committed)."""
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parents[2]

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env", overwrite=False)

SECRET_KEY = env("ETQA_SECRET_KEY", default="")
DEBUG = env.bool("ETQA_DEBUG", default=False)
ALLOWED_HOSTS = env.list("ETQA_ALLOWED_HOSTS", default=["127.0.0.1", "localhost"])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "rest_framework",
    # ETqa modules (ADR-01). Lower layers first.
    "apps.audit",
    "apps.sysconfig",
    "apps.accounts",
    "apps.access",
    "apps.jobs",
    "apps.ai",
    "apps.documents",
    "apps.retrieval",
    "apps.ingestion",
    "apps.chat",
    "apps.testcases",
    "apps.ops",
    "apps.ui",
]

MIDDLEWARE = [
    "apps.audit.middleware.RequestIdMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",  # static files under Waitress (no separate web server)
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.accounts.middleware.AbsoluteSessionTimeoutMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "django.template.context_processors.i18n",
                "apps.ui.context.ui_language",
            ],
        },
    },
]

DATABASES = {
    "default": env.db_url("ETQA_DATABASE_URL", default="postgres://etqa:etqa@127.0.0.1:5432/etqa"),
}
DATABASES["default"]["CONN_MAX_AGE"] = env.int("ETQA_DB_CONN_MAX_AGE", default=60)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True
DATABASES["default"].setdefault("OPTIONS", {})["connect_timeout"] = 5

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "ui:home"
LOGOUT_REDIRECT_URL = "login"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Sessions (section 6): idle timeout via cookie age refreshed on each request,
# absolute timeout enforced by AbsoluteSessionTimeoutMiddleware.
SESSION_IDLE_MINUTES = env.int("ETQA_SESSION_IDLE_MINUTES", default=60)
SESSION_ABSOLUTE_HOURS = env.int("ETQA_SESSION_ABSOLUTE_HOURS", default=8)
SESSION_COOKIE_AGE = SESSION_IDLE_MINUTES * 60
SESSION_SAVE_EVERY_REQUEST = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"

# Login throttling (section 6). Single web process -> local memory cache is sufficient;
# switch to DatabaseCache if more than one web process is ever run.
LOGIN_MAX_FAILURES = env.int("ETQA_LOGIN_MAX_FAILURES", default=5)
LOGIN_MAX_FAILURES_PER_IP = env.int("ETQA_LOGIN_MAX_FAILURES_PER_IP", default=20)
LOGIN_LOCK_MINUTES = env.int("ETQA_LOGIN_LOCK_MINUTES", default=15)
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "etqa"}}

# Only trust X-Forwarded-Proto when a TLS terminator is in front of Waitress (ADR-03).
if env.bool("ETQA_BEHIND_TLS_PROXY", default=False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = env.bool("ETQA_SSL_REDIRECT", default=True)
    # HSTS stays off until the TLS setup is final; enabling it carelessly locks browsers to HTTPS.
    SECURE_HSTS_SECONDS = env.int("ETQA_HSTS_SECONDS", default=0)

LANGUAGE_CODE = "en"
LANGUAGES = [("en", "English"), ("ar", "العربية")]
TIME_ZONE = "Africa/Cairo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STATIC_ROOT.mkdir(exist_ok=True)  # WhiteNoise warns on every request if it is missing
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# Original documents live outside the web root and are never served by path (ADR-11).
ETQA_FILE_ROOT = Path(env("ETQA_FILE_ROOT", default=str(BASE_DIR / "media"))).resolve()

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],  # deny by default
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.LimitOffsetPagination",
    "PAGE_SIZE": 50,
}

ETQA_VERSION = "0.6.0"
ETQA_SERVE_HOST = env("ETQA_SERVE_HOST", default="127.0.0.1")
ETQA_SERVE_PORT = env.int("ETQA_SERVE_PORT", default=8000)
ETQA_SERVE_THREADS = env.int("ETQA_SERVE_THREADS", default=8)

LOG_DIR = Path(env("ETQA_LOG_DIR", default=str(BASE_DIR / "logs"))).resolve()
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"request_id": {"()": "apps.audit.logging.RequestIdFilter"}},
    "formatters": {"json": {"()": "apps.audit.logging.JsonFormatter"}},
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "json", "filters": ["request_id"]},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {"django.db.backends": {"level": "WARNING"}},
}


def add_file_logging(logging_config: dict, log_dir: Path) -> None:
    """Rotating JSON log file; called by dev/prod settings, not by tests."""
    log_dir.mkdir(parents=True, exist_ok=True)
    logging_config["handlers"]["file"] = {
        "class": "logging.handlers.RotatingFileHandler",
        "filename": str(log_dir / "etqa.log"),
        "maxBytes": 10 * 1024 * 1024,
        "backupCount": 10,
        "encoding": "utf-8",
        "formatter": "json",
        "filters": ["request_id"],
    }
    logging_config["root"]["handlers"].append("file")

# Uploads stream to disk above 2.5 MB; the per-type limit is a runtime setting (upload.max_mb).
FILE_UPLOAD_MAX_MEMORY_SIZE = 2_621_440
DATA_UPLOAD_MAX_MEMORY_SIZE = 5_242_880
