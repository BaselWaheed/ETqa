from django.apps import AppConfig


class AiConfig(AppConfig):
    name = "apps.ai"
    label = "ai"
    verbose_name = "AI models"

    def ready(self) -> None:
        from apps.jobs.registry import register_queue_gate

        from .health import ollama_available

        # Inference workers stop claiming while Ollama is down; jobs stay queued (section 5, availability).
        register_queue_gate("inference", ollama_available)
