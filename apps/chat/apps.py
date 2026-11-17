from django.apps import AppConfig


class ChatConfig(AppConfig):
    name = "apps.chat"
    label = "chat"
    verbose_name = "Chat"

    def ready(self) -> None:
        from . import handlers  # noqa: F401
