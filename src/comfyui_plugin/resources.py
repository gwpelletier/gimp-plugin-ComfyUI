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


def workflow_supports_vae(workflow: dict[str, Any]) -> bool:
    """Return whether an API workflow exposes a selectable VAE input."""
    return any(
        node.get("class_type") in {"VAELoader", "CheckpointLoader", "CheckpointLoaderSimple"}
        and ("vae_name" in node.get("inputs", {}) or node.get("class_type") == "VAELoader")
        for node in workflow.values()
        if isinstance(node, dict)
    )


class CheckpointType(str, Enum):
    """Model families used to select generation defaults."""

    AUTO = "Auto"
    FLUX = "Flux"
    SDXL = "SDXL"
    SD15 = "SD 1.5"
    KREA2 = "Krea 2"
    CUSTOM = "Custom"


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
    CheckpointType.FLUX: CheckpointProfile(CheckpointType.FLUX, "high", "workflow", 20, 3.5, "euler", "normal", 0.75),
    CheckpointType.SDXL: CheckpointProfile(CheckpointType.SDXL, "high", "workflow", 30, 7.0, "euler", "normal", 0.8),
    CheckpointType.SD15: CheckpointProfile(CheckpointType.SD15, "medium", "checkpoint name", 20, 7.5, "euler", "normal", 0.65),
    CheckpointType.KREA2: CheckpointProfile(CheckpointType.KREA2, "high", "workflow", 28, 4.0, "euler", "normal", 1.0),
    CheckpointType.CUSTOM: CheckpointProfile(CheckpointType.CUSTOM, "low", "override", 20, 8.0, "euler", "normal", 1.0),
}


def infer_checkpoint_type(workflow: dict[str, Any], checkpoint: str = "") -> CheckpointType:
    """Infer a checkpoint family from workflow structure, then its name."""
    classes = {node.get("class_type") for node in workflow.values() if isinstance(node, dict)}
    if "Krea2ImageNode" in classes:
        return CheckpointType.KREA2
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
        return CheckpointType.KREA2
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
    if checkpoint_type == CheckpointType.KREA2 and "Krea2ImageNode" not in classes:
        raise ValueError("Krea 2 models require a workflow with Krea2ImageNode")


def workflow_matches_checkpoint_type(workflow: dict[str, Any], checkpoint_type: CheckpointType) -> bool:
    """Return whether a workflow belongs to an explicit family selection."""
    return checkpoint_type == CheckpointType.AUTO or infer_checkpoint_type(workflow) == checkpoint_type