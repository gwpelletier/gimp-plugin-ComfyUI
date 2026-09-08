"""ComfyUI resource option helpers independent of GIMP and GTK."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Any


def filter_options(options: list[str], query: str) -> list[str]:
    """Return options containing ``query`` while preserving server order."""
    normalized_query = query.strip().casefold()
    if not normalized_query:
        return list(options)
    return [option for option in options if normalized_query in option.casefold()]


def best_guess_option(options: list[str], hints: tuple[str, ...], current: str = "") -> str | None:
    """Choose a resource by preserving ``current`` or matching a name hint."""
    if current in options:
        return current
    normalized_options = [(option, option.casefold()) for option in options]
    normalized_hints = tuple(hint.casefold() for hint in hints)
    for option, normalized_option in normalized_options:
        if any(hint in normalized_option for hint in normalized_hints):
            return option
    return options[0] if len(options) == 1 else None


_RESOURCE_MARKERS = {
    "checkpoint",
    "vae",
    "unet",
    "clip_l",
    "clip_t5",
    "diffusion_model",
    "krea_clip",
}


def required_workflow_resources(workflow: dict[str, Any]) -> tuple[str, ...]:
    """Return model resources required by workflow markers and loader nodes."""
    required: list[str] = []
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs", {})
        if not isinstance(inputs, dict):
            continue
        for value in inputs.values():
            if isinstance(value, str) and value.startswith("{{") and value.endswith("}}"):
                marker = value[2:-2].strip()
                if marker in _RESOURCE_MARKERS and marker not in required:
                    required.append(marker)
        class_type = node.get("class_type")
        fallback = {
            "CheckpointLoader": "checkpoint",
            "CheckpointLoaderSimple": "checkpoint",
            "VAELoader": "vae",
            "DualCLIPLoader": "clip_l",
        }.get(class_type)
        if fallback and fallback not in required:
            required.append(fallback)
        if class_type == "DualCLIPLoader" and "clip_t5" not in required:
            required.append("clip_t5")
        if class_type == "UNETLoader" and "unet" not in required and "diffusion_model" not in required:
            required.append("unet")
        if class_type == "DiffusionModelLoader" and "diffusion_model" not in required:
            required.append("diffusion_model")
        if class_type == "CLIPLoader" and node.get("inputs", {}).get("type") == "krea2":
            if "krea_clip" not in required:
                required.append("krea_clip")
    return tuple(required)


def missing_workflow_resources(workflow: dict[str, Any], values: dict[str, str | None]) -> tuple[str, ...]:
    """Return required workflow resources that have no selected value."""
    return tuple(resource for resource in required_workflow_resources(workflow) if not values.get(resource))


def workflow_supports_vae(workflow: dict[str, Any]) -> bool:
    """Return whether an API workflow exposes a selectable VAE input."""
    return any(
        node.get("class_type") in {"VAELoader", "CheckpointLoader", "CheckpointLoaderSimple"}
        and ("vae_name" in node.get("inputs", {}) or node.get("class_type") == "VAELoader")
        for node in workflow.values()
        if isinstance(node, dict)
    )


def workflow_supports_inpainting(workflow: dict[str, Any]) -> bool:
    """Return whether an API workflow exposes a mask input for inpainting."""
    return any(
        isinstance(node, dict) and "mask" in node.get("inputs", {})
        for node in workflow.values()
    )


class CheckpointType(str, Enum):
    """Model families used to select generation defaults."""

    AUTO = "Auto"
    FLUX = "Flux"
    SDXL = "SDXL"
    SD15 = "SD 1.5"
    KREA2_TURBO = "Krea2-Turbo"
    CUSTOM = "Custom"


def family_supports_mode(family: CheckpointType, mode: str) -> bool:
    """Return whether a model family supports the selected generation mode."""
    return not (mode == "Inpainting" and family == CheckpointType.KREA2_TURBO)


@dataclass(frozen=True)
class CheckpointProfile:
    """Inferred checkpoint family and conservative generation defaults."""

    checkpoint_type: CheckpointType
    confidence: str
    source: str
    steps: int
    cfg: float
    sampler: str
    scheduler: str
    denoise: float


_PROFILES = {
    CheckpointType.FLUX: CheckpointProfile(CheckpointType.FLUX, "high", "workflow", 16, 1.0, "euler", "simple", 0.75),
    CheckpointType.SDXL: CheckpointProfile(CheckpointType.SDXL, "high", "workflow", 30, 7.0, "dpmpp_2m", "karras", 0.8),
    CheckpointType.SD15: CheckpointProfile(CheckpointType.SD15, "medium", "checkpoint name", 20, 7.5, "dpmpp_2m", "karras", 0.65),
    CheckpointType.KREA2_TURBO: CheckpointProfile(CheckpointType.KREA2_TURBO, "high", "workflow", 8, 1.0, "euler", "normal", 1.0),
    CheckpointType.CUSTOM: CheckpointProfile(CheckpointType.CUSTOM, "low", "override", 20, 8.0, "euler", "normal", 1.0),
}


def infer_checkpoint_type(workflow: dict[str, Any], checkpoint: str = "") -> CheckpointType:
    """Infer a checkpoint family from workflow structure, then its name."""
    classes = {node.get("class_type") for node in workflow.values() if isinstance(node, dict)}
    has_krea_clip = any(
        node.get("class_type") == "CLIPLoader"
        and node.get("inputs", {}).get("type") == "krea2"
        for node in workflow.values()
        if isinstance(node, dict)
    )
    if ("UNETLoader" in classes or "DiffusionModelLoader" in classes) and has_krea_clip:
        return CheckpointType.KREA2_TURBO
    if "UNETLoader" in classes or "DualCLIPLoader" in classes:
        return CheckpointType.FLUX
    if "CLIPTextEncodeSDXL" in classes or "CLIPTextEncodeSDXLRefiner" in classes:
        return CheckpointType.SDXL
    if "CheckpointLoaderSimple" in classes and "CLIPTextEncode" in classes:
        return CheckpointType.SD15
    normalized = checkpoint.casefold()
    if any(marker in normalized for marker in ("flux", "schnell", "dev", "t5xxl")):
        return CheckpointType.FLUX
    if any(marker in normalized for marker in ("sdxl", "sd_xl", "xl_base", "xl_refiner")):
        return CheckpointType.SDXL
    if any(marker in normalized for marker in ("sd15", "sd-1.5", "1.5", "dreamshaper")):
        return CheckpointType.SD15
    if "krea" in normalized:
        return CheckpointType.KREA2_TURBO
    return CheckpointType.CUSTOM


def checkpoint_profile(
    workflow: dict[str, Any],
    checkpoint: str = "",
    override: CheckpointType = CheckpointType.AUTO,
) -> CheckpointProfile:
    """Return defaults using an explicit override or conservative inference."""
    if override != CheckpointType.AUTO:
        return _PROFILES[override]
    inferred = infer_checkpoint_type(workflow, checkpoint)
    profile = _PROFILES[inferred]
    if inferred == CheckpointType.CUSTOM:
        return CheckpointProfile(inferred, "unknown", "no reliable signal", 20, 8.0, "euler", "normal", 1.0)
    classes = {node.get("class_type") for node in workflow.values() if isinstance(node, dict)}
    workflow_signal = bool(
        {"UNETLoader", "DualCLIPLoader", "CLIPTextEncodeSDXL", "CLIPTextEncodeSDXLRefiner"} & classes
    )
    return replace(
        profile,
        confidence="high" if workflow_signal else "medium",
        source="workflow" if workflow_signal else "checkpoint name",
    )


def validate_checkpoint_workflow(checkpoint_type: CheckpointType, workflow: dict[str, Any]) -> None:
    """Reject a model/workflow family mismatch before queueing work."""
    classes = {node.get("class_type") for node in workflow.values() if isinstance(node, dict)}
    if checkpoint_type == CheckpointType.FLUX and not {"UNETLoader", "DualCLIPLoader"} <= classes:
        raise ValueError("Flux models require a workflow with UNETLoader and DualCLIPLoader")
    if checkpoint_type == CheckpointType.SDXL and "CLIPTextEncodeSDXL" not in classes:
        raise ValueError("SDXL models require a workflow with CLIPTextEncodeSDXL nodes")
    if checkpoint_type == CheckpointType.SD15 and not {"CheckpointLoaderSimple", "CLIPTextEncode"} <= classes:
        raise ValueError("SD 1.5 models require a classic CheckpointLoaderSimple workflow")
    has_krea_clip = any(
        node.get("class_type") == "CLIPLoader"
        and node.get("inputs", {}).get("type") == "krea2"
        for node in workflow.values()
        if isinstance(node, dict)
    )
    has_diffusion_loader = bool({"UNETLoader", "DiffusionModelLoader"} & classes)
    if checkpoint_type == CheckpointType.KREA2_TURBO and not (
        has_diffusion_loader and "VAELoader" in classes and has_krea_clip
    ):
        raise ValueError("Krea2-Turbo models require Diffusion Model, Krea2 CLIP, and VAE loaders")


def workflow_matches_checkpoint_type(workflow: dict[str, Any], checkpoint_type: CheckpointType) -> bool:
    """Return whether a workflow belongs to an explicit family selection."""
    return checkpoint_type == CheckpointType.AUTO or infer_checkpoint_type(workflow) == checkpoint_type