from django.db import models


class AIModel(models.Model):
    class Kind(models.TextChoices):
        GENERATE = "generate"
        EMBED = "embed"
        VISION = "vision"

    key = models.SlugField(max_length=60, unique=True, help_text="Stable name used in routes, e.g. main-llm.")
    runtime = models.CharField(max_length=20, default="ollama")
    runtime_name = models.CharField(max_length=120, help_text="The model tag in the runtime, e.g. qwen2.5:7b-instruct-q4_K_M.")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    family = models.CharField(max_length=60, blank=True)
    quantization = models.CharField(max_length=20, blank=True)
    license = models.CharField(max_length=60, blank=True)
    context_limit = models.PositiveIntegerField(default=8192)
    dims = models.PositiveIntegerField(null=True, blank=True, help_text="Embedding models: vector dimensions.")
    est_ram_mb = models.PositiveIntegerField(default=0)
    timeout_s = models.PositiveIntegerField(default=300)
    keep_alive = models.CharField(max_length=10, default="5m", help_text="Ollama keep_alive, e.g. 30m, 0, -1.")
    num_thread = models.PositiveIntegerField(null=True, blank=True)
    tokenizer_path = models.CharField(max_length=300, blank=True, help_text="Local tokenizer.json for exact token counts (U12).")
    enabled = models.BooleanField(default=True)

    class Meta:
        ordering = ["kind", "key"]

    def __str__(self) -> str:
        return f"{self.key} ({self.runtime_name})"


class TaskRoute(models.Model):
    task = models.CharField(max_length=40)
    model = models.ForeignKey(AIModel, on_delete=models.PROTECT, related_name="routes")
    priority = models.PositiveIntegerField(default=1, help_text="1 = first choice; higher numbers are fallbacks.")
    max_tokens = models.PositiveIntegerField(default=700)
    temperature = models.FloatField(default=0.1)
    no_downgrade = models.BooleanField(default=False, help_text="Never fall back to another model for this task.")

    class Meta:
        ordering = ["task", "priority"]
        constraints = [models.UniqueConstraint(fields=["task", "priority"], name="uniq_task_priority")]

    def __str__(self) -> str:
        return f"{self.task} -> {self.model.key} (#{self.priority})"


class PromptTemplate(models.Model):
    """Optional override of a built-in prompt. The active row for a task replaces the code default."""

    task = models.CharField(max_length=40)
    version = models.PositiveIntegerField(default=1)
    body = models.TextField()
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["task", "version"], name="uniq_prompt_version"),
            models.UniqueConstraint(fields=["task"], condition=models.Q(is_active=True), name="one_active_prompt"),
        ]


class AIExecution(models.Model):
    """One model call. Holds timing and token counts, never prompt or answer text."""

    created_at = models.DateTimeField(auto_now_add=True)
    task = models.CharField(max_length=40)
    model_key = models.CharField(max_length=60)
    job_id = models.BigIntegerField(null=True, blank=True)
    prompt_tokens_est = models.PositiveIntegerField(default=0)
    prompt_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    load_ms = models.PositiveIntegerField(default=0)
    total_ms = models.PositiveIntegerField(default=0)
    first_token_ms = models.PositiveIntegerField(null=True, blank=True)
    outcome = models.CharField(max_length=20)
    error_code = models.CharField(max_length=60, blank=True)

    class Meta:
        indexes = [models.Index(fields=["task", "created_at"])]
