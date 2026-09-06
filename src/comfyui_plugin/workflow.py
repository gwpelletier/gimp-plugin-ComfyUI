"""Workflow loading and parameter substitution helpers."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any


class WorkflowError(ValueError):
    """Raised for invalid or unsupported workflow templates."""


def load_workflow(path: str | Path) -> dict[str, Any]:
    try:
        workflow = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise WorkflowError(f"Unable to read workflow {path}: {error}") from error
    if not isinstance(workflow, dict):
        raise WorkflowError("Workflow must be a JSON object")
    return workflow


def apply_parameters(workflow: dict[str, Any], parameters: dict[str, Any]) -> dict[str, Any]:
    """Replace marked node inputs without mutating the loaded template."""
    result = copy.deepcopy(workflow)
    for node in result.values():
        if not isinstance(node, dict) or "inputs" not in node:
            continue
        inputs = node["inputs"]
        if not isinstance(inputs, dict):
            continue
        for key, value in list(inputs.items()):
            if isinstance(value, str) and value.startswith("{{") and value.endswith("}}"):
                name = value[2:-2].strip()
                if name in parameters:
                    inputs[key] = parameters[name]
    return result