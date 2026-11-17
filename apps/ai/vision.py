"""Exclusive vision window (section 5): unload text models, confirm, run a capped batch, unload vision."""
from __future__ import annotations

import time

from apps.sysconfig.services import get as setting

from . import client
from .models import AIModel


class WindowNotReady(Exception):
    pass


class VisionWindow:
    def __init__(self):
        self.started = None
        self.count = 0
        self.vision: AIModel | None = None

    def open(self, vision_model: AIModel) -> None:
        text_models = AIModel.objects.filter(enabled=True, kind=AIModel.Kind.GENERATE)
        for model in text_models:
            client.unload(model.runtime_name)
        still = set(client.loaded()) & {m.runtime_name for m in text_models}
        if still:
            raise WindowNotReady(f"text models did not unload: {sorted(still)}")
        self.started, self.vision = time.monotonic(), vision_model

    def has_room(self) -> bool:
        return (self.count < setting("vision.window_max_jobs")
                and time.monotonic() - self.started < setting("vision.window_max_minutes") * 60)

    def close(self) -> None:
        if self.vision is not None:
            try:
                client.unload(self.vision.runtime_name)
            except client.ModelError:
                pass
