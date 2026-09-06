"""ComfyUI resource option helpers independent of GIMP and GTK."""

from __future__ import annotations

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