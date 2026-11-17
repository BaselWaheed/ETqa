from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403
from .base import ALLOWED_HOSTS, LOG_DIR, LOGGING, SECRET_KEY, add_file_logging

DEBUG = False
if len(SECRET_KEY) < 50:
    raise ImproperlyConfigured("ETQA_SECRET_KEY must be set to a random value of at least 50 characters.")
if not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS:
    raise ImproperlyConfigured("ETQA_ALLOWED_HOSTS must list explicit host names.")
add_file_logging(LOGGING, LOG_DIR)
