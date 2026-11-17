from django.apps import AppConfig


class IngestionConfig(AppConfig):
    name = "apps.ingestion"
    label = "ingestion"
    verbose_name = "Ingestion"

    def ready(self) -> None:
        from . import handlers  # noqa: F401  (registers job handlers)
