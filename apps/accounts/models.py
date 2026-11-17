from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Local account (decision log: local accounts; AD can be added later as an auth backend)."""

    class Language(models.TextChoices):
        ENGLISH = "en", "English"
        ARABIC = "ar", "العربية"

    preferred_language = models.CharField(max_length=2, choices=Language.choices, default=Language.ENGLISH)
