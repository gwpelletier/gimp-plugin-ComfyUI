"""Thread-safe generation orchestration between GIMP and ComfyUI."""

from __future__ import annotations

import random
import threading
from dataclasses import dataclass
from dataclasses import replace
from pathlib import Path
from typing import Callable

from .batch import BatchItem, BatchQueue, BatchSummary
from .client import (
    ComfyImage,
    ComfyUICancelledError,
    ComfyUIClient,
    ComfyUIEvent,
    ComfyUIEventType,
)
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
    vae: str | None = None
    unet: str | None = None
    clip_l: str | None = None
    clip_t5: str | None = None
    input_image: str | None = None
    mask_image: str | None = None
    seed: int = -1
    width: int | None = None
    height: int | None = None
    steps: int = 20
    cfg: float = 8.0
    sampler: str = "euler"
    scheduler: str = "normal"
    denoise: float = 1.0
    loras: dict[str, float] | None = None
    diffusion_model: str | None = None
    krea_clip: str | None = None


@dataclass(frozen=True)
class GenerationResult:
    """Prompt identifier, resolved seed, and image outputs returned by ComfyUI."""

    prompt_id: str
    seed: int
    images: list[ComfyImage]


class GenerationCancelledError(RuntimeError):
    """Raised when generation is cancelled before outputs are available."""


class GenerationCoordinator:
    """Submit prepared workflows and report progress without owning GIMP UI."""

    def __init__(self, client: ComfyUIClient):
        """Create a coordinator using an already configured ComfyUI client."""
        self.client = client
        self._active_prompt_ids: set[str] = set()
        self._cancellation_events: set[threading.Event] = set()
        self._state_lock = threading.Lock()

    @property
    def active_prompt_ids(self) -> tuple[str, ...]:
        """Return prompt IDs currently being polled by this coordinator."""
        with self._state_lock:
            return tuple(sorted(self._active_prompt_ids))

    def cancel(self) -> None:
        """Request cancellation of active work and interrupt ComfyUI."""
        with self._state_lock:
            events = tuple(self._cancellation_events)
        for event in events:
            event.set()
        if events:
            self.client.interrupt()

    def run(
        self,
        request: GenerationRequest,
        *,
        on_progress: Callable[[int, int], None] | None = None,
        on_event: Callable[[ComfyUIEvent], None] | None = None,
        cancellation_event: threading.Event | None = None,
    ) -> GenerationResult:
        """Prepare, queue, wait for, and return one generation result."""
        cancellation_event = cancellation_event or threading.Event()
        with self._state_lock:
            self._cancellation_events.add(cancellation_event)
        try:
            return self._run(request, on_progress, on_event, cancellation_event)
        finally:
            with self._state_lock:
                self._cancellation_events.discard(cancellation_event)

    def run_batch(
        self,
        requests: list[GenerationRequest],
        *,
        max_retries: int = 0,
        cancellation_event: threading.Event | None = None,
        on_update: Callable[[BatchItem[GenerationRequest, GenerationResult]], None] | None = None,
    ) -> BatchSummary[GenerationResult]:
        """Run requests sequentially while retaining partial successes."""
        items = [BatchItem(str(index), request) for index, request in enumerate(requests)]
        queue = BatchQueue[GenerationRequest, GenerationResult](max_retries=max_retries)
        return queue.run(
            items,
            self.run,
            cancellation_event=cancellation_event,
            on_update=on_update,
        )

    def _run(
        self,
        request: GenerationRequest,
        on_progress: Callable[[int, int], None] | None,
        on_event: Callable[[ComfyUIEvent], None] | None,
        cancellation_event: threading.Event,
    ) -> GenerationResult:
        if cancellation_event.is_set():
            raise GenerationCancelledError("Generation was cancelled before queueing")
        seed = request.seed if request.seed > 0 else random.randint(1, 2**32)
        workflow = apply_generation_parameters(
            request.workflow,
            input_image=request.input_image,
            mask_image=request.mask_image,
            positive_prompt=request.prompt,
            negative_prompt=request.negative_prompt,
            checkpoint=request.checkpoint,
            vae=request.vae,
            unet=request.unet,
            clip_l=request.clip_l,
            clip_t5=request.clip_t5,
            diffusion_model=request.diffusion_model,
            krea_clip=request.krea_clip,
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
        with self._state_lock:
            self._active_prompt_ids.add(prompt_id)
        observer_stop = threading.Event()
        observer = self._start_websocket_observer(prompt_id, workflow, observer_stop, on_progress, on_event)
        try:
            images = self.client.wait_for_outputs(prompt_id, cancellation_event=cancellation_event)
        except ComfyUICancelledError as error:
            raise GenerationCancelledError(str(error)) from error
        finally:
            observer_stop.set()
            if observer is not None:
                observer.join(timeout=1)
            with self._state_lock:
                self._active_prompt_ids.discard(prompt_id)
        if cancellation_event.is_set():
            raise GenerationCancelledError(f"Generation {prompt_id} was cancelled")
        if on_progress:
            on_progress(1, 1)
        return GenerationResult(prompt_id, seed, images)

    def _start_websocket_observer(
        self,
        prompt_id: str,
        workflow: dict,
        stop_event: threading.Event,
        on_progress: Callable[[int, int], None] | None,
        on_event: Callable[[ComfyUIEvent], None] | None,
    ) -> threading.Thread | None:
        open_websocket = getattr(self.client, "open_websocket", None)
        if open_websocket is None:
            return None

        def observe() -> None:
            websocket = None
            try:
                websocket = open_websocket(timeout=2)
                websocket.connect()
                while not stop_event.is_set():
                    event = websocket.receive()
                    if event is None or not isinstance(event, ComfyUIEvent):
                        continue
                    if event.prompt_id not in {None, prompt_id}:
                        continue
                    if event.node_id is not None:
                        node = workflow.get(event.node_id)
                        if isinstance(node, dict) and isinstance(node.get("class_type"), str):
                            event = replace(event, node_type=node["class_type"])
                    if on_event is not None:
                        on_event(event)
                    if event.event_type == ComfyUIEventType.PROGRESS and on_progress is not None:
                        on_progress(event.value or 0, event.maximum or 0)
                    if event.event_type in {
                        ComfyUIEventType.EXECUTED,
                        ComfyUIEventType.EXECUTION_ERROR,
                    }:
                        break
            except Exception:
                # REST history remains authoritative when WebSocket is unavailable.
                return
            finally:
                if websocket is not None:
                    websocket.close()

        observer = threading.Thread(target=observe, daemon=True)
        observer.start()
        return observer