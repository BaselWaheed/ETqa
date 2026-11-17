from django.core.management.base import BaseCommand
from django.db import transaction

from apps.ai.models import AIModel, TaskRoute

MODELS = [
    dict(key="main-llm", runtime_name="qwen2.5:7b-instruct-q4_K_M", kind="generate", family="Qwen2.5",
         quantization="Q4_K_M", license="Apache-2.0", context_limit=8192, est_ram_mb=5500, timeout_s=600, keep_alive="30m"),
    dict(key="slm", runtime_name="qwen2.5:1.5b-instruct-q4_K_M", kind="generate", family="Qwen2.5",
         quantization="Q4_K_M", license="Apache-2.0", context_limit=4096, est_ram_mb=1200, timeout_s=120, keep_alive="5m"),
    dict(key="embed-bge-m3", runtime_name="bge-m3", kind="embed", family="BGE-M3", license="MIT",
         context_limit=8192, dims=1024, est_ram_mb=1200, timeout_s=300, keep_alive="30m"),
    dict(key="vision", runtime_name="qwen3-vl:4b", kind="vision", family="Qwen3-VL", license="Apache-2.0",
         context_limit=4096, est_ram_mb=4000, timeout_s=900, keep_alive="0"),
]
ROUTES = [
    ("chat.answer", "main-llm", 1, 700, 0.1, False),
    ("tc.generate", "main-llm", 1, 2500, 0.2, True),
    ("intent.classify", "slm", 1, 40, 0.0, False),
    ("query.rewrite", "slm", 1, 80, 0.0, False),
    ("embed", "embed-bge-m3", 1, 0, 0.0, True),
    ("vision.describe", "vision", 1, 600, 0.1, True),
]


class Command(BaseCommand):
    help = "Create the default model registry and task routes (section 5). Existing rows are left unchanged."

    @transaction.atomic
    def handle(self, *args, **options):
        for spec in MODELS:
            _, created = AIModel.objects.get_or_create(key=spec["key"], defaults=spec)
            self.stdout.write(f"{'created' if created else 'kept'} model {spec['key']}")
        for task, key, prio, max_tokens, temp, no_down in ROUTES:
            TaskRoute.objects.get_or_create(task=task, priority=prio, defaults=dict(
                model=AIModel.objects.get(key=key), max_tokens=max_tokens, temperature=temp, no_downgrade=no_down))
        self.stdout.write("Model tags are starting points; confirm them with `ollama list` (Phase 0).")
