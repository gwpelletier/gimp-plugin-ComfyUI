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


_PROFILES = {
    CheckpointType.FLUX: CheckpointProfile(CheckpointType.FLUX, "high", "workflow", 20, 3.5, "euler", "normal"),
    CheckpointType.SDXL: CheckpointProfile(CheckpointType.SDXL, "high", "workflow", 30, 7.0, "euler", "normal"),
    CheckpointType.SD15: CheckpointProfile(CheckpointType.SD15, "medium", "checkpoint name", 20, 7.5, "euler", "normal"),
    CheckpointType.CUSTOM: CheckpointProfile(CheckpointType.CUSTOM, "low", "override", 20, 8.0, "euler", "normal"),
}


def infer_checkpoint_type(workflow: dict[str, Any], checkpoint: str = "") -> CheckpointType:
    """Infer a checkpoint family from workflow structure, then its name."""
    classes = {node.get("class_type") for node in workflow.values() if isinstance(node, dict)}
    if "UNETLoader" in classes or "DualCLIPLoader" in classes:
        return CheckpointType.FLUX
    if "CLIPTextEncodeSDXL" in classes or "CLIPTextEncodeSDXLRefiner" in classes:
        return CheckpointType.SDXL
    normalized = checkpoint.casefold()
    if any(marker in normalized for marker in ("flux", "schnell", "dev", "t5xxl")):
        return CheckpointType.FLUX
    if any(marker in normalized for marker in ("sdxl", "sd_xl", "xl_base", "xl_refiner")):
        return CheckpointType.SDXL
    if any(marker in normalized for marker in ("sd15", "sd-1.5", "1.5", "dreamshaper")):
        return CheckpointType.SD15
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
        return CheckpointProfile(inferred, "unknown", "no reliable signal", 20, 8.0, "euler", "normal")
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