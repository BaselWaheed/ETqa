from django.apps import AppConfig


class TestcasesConfig(AppConfig):
    name = "apps.testcases"
    label = "testcases"
    verbose_name = "Test cases"

    def ready(self) -> None:
        from . import handlers  # noqa: F401
