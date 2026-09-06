"""Thread-safe generation orchestration between GIMP and ComfyUI."""

from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .client import ComfyImage, ComfyUIClient
from .workflow import apply_generation_parameters


def parse_lora_settings(value: str) -> dict[str, float]:
    """Parse ``name:strength`` LoRA entries from a dialog field.

    Empty input returns no LoRAs. Entries are comma-separated and a missing
    strength defaults to ``1.0``.

    Raises:
        ValueError: If a strength is not numeric or a name is empty.
    """
    loras = {}
    for entry in value.split(","):
        entry = entry.strip()
        if not entry:
            continue
        name, separator, strength_text = entry.partition(":")
        name = name.strip()
        if not name:
            raise ValueError("LoRA name must not be empty")
        try:
            strength = float(strength_text) if separator else 1.0
        except ValueError as error:
            raise ValueError(f"Invalid LoRA strength for {name!r}") from error
        loras[name] = strength
    return loras


@dataclass(frozen=True)
class GenerationRequest:
    """Inputs required to submit one image generation request.

    A negative seed requests a generated seed. Numeric and sampler defaults are
    valid for the bundled KSampler workflow and can be overridden per request.
    """

    workflow: dict
    prompt: str
    negative_prompt: str
    checkpoint: str | None = None
    input_image: str | None = None
    seed: int = -1
    width: int | None = None
    height: int | None = None
    steps: int = 20
    cfg: float = 8.0
    sampler: str = "euler"
    scheduler: str = "normal"
    denoise: float = 1.0
    loras: dict[str, float] | None = None


@dataclass(frozen=True)
class GenerationResult:
    """Prompt identifier and image outputs returned by ComfyUI."""

    prompt_id: str
    images: list[ComfyImage]


class GenerationCoordinator:
    """Submit prepared workflows and report progress without owning GIMP UI."""

    def __init__(self, client: ComfyUIClient):
        """Create a coordinator using an already configured ComfyUI client."""
        self.client = client

    def run(
        self,
        request: GenerationRequest,
        *,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> GenerationResult:
        """Prepare, queue, wait for, and return one generation result."""
        seed = request.seed if request.seed > 0 else random.randint(1, 2**32)
        workflow = apply_generation_parameters(
            request.workflow,
            input_image=request.input_image,
            positive_prompt=request.prompt,
            negative_prompt=request.negative_prompt,
            checkpoint=request.checkpoint,
            seed=seed,
            width=request.width,
            height=request.height,
            steps=request.steps,
            cfg=request.cfg,
            sampler=request.sampler,
            scheduler=request.scheduler,
            denoise=request.denoise,
            loras=request.loras,
        )
        prompt_id = self.client.queue_prompt(workflow)
        images = self.client.wait_for_outputs(prompt_id)
        if on_progress:
            on_progress(1, 1)
        return GenerationResult(prompt_id, images)