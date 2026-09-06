"""Workflow loading and parameter substitution helpers.

Workflow preparation behavior is adapted from the GPL-3.0-only
``gimp-comfy-tools`` project and kept independent of GIMP bindings.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any


class WorkflowError(ValueError):
    """Raised for invalid or unsupported workflow templates."""


def validate_resolved_workflow(workflow: dict[str, Any]) -> None:
    """Reject templates that still contain unresolved parameter markers.

    Raises:
        WorkflowError: If any node input still contains a ``{{parameter}}`` marker.
    """
    unresolved = []
    for node_id, node in workflow.items():
        for input_name, value in node.get("inputs", {}).items():
            if isinstance(value, str) and value.startswith("{{") and value.endswith("}}"):
                unresolved.append(f"{node_id}.{input_name}={value}")
    if unresolved:
        raise WorkflowError("Unresolved workflow parameters: " + ", ".join(unresolved))


def validate_api_workflow(workflow: dict[str, Any]) -> None:
    """Validate the node-map shape expected by ComfyUI's execution API.

    Raises:
        WorkflowError: If the workflow is UI-format or contains malformed nodes.
    """
    if "nodes" in workflow:
        raise WorkflowError("Workflow must use ComfyUI API format, not UI workflow format")
    for node_id, node in workflow.items():
        if not isinstance(node, dict) or not isinstance(node.get("class_type"), str):
            raise WorkflowError(f"Workflow node {node_id!r} is missing class_type")
        if not isinstance(node.get("inputs"), dict):
            raise WorkflowError(f"Workflow node {node_id!r} is missing inputs")


def validate_workflow_compatibility(
    workflow: dict[str, Any],
    object_info: dict[str, Any],
) -> None:
    """Reject workflows that reference unavailable nodes or inputs.

    ``object_info`` is the schema returned by ComfyUI. Enumerated resource
    values are checked when the server advertises a concrete option list.
    """
    validate_api_workflow(workflow)
    problems = []
    for node_id, node in workflow.items():
        class_type = node["class_type"]
        schema = object_info.get(class_type)
        if not isinstance(schema, dict):
            problems.append(f"{node_id} uses unavailable node {class_type}")
            continue
        schema_inputs = {}
        for section in ("required", "optional"):
            schema_inputs.update(schema.get("input", {}).get(section, {}))
        for input_name, value in node["inputs"].items():
            if input_name not in schema_inputs:
                if class_type in {"LoadImage", "LoadImageMask"} and input_name == "upload":
                    continue
                problems.append(f"{node_id}.{input_name} is unsupported by {class_type}")
                continue
            if isinstance(value, list):
                continue
            definition = schema_inputs[input_name]
            if isinstance(definition, list) and definition and isinstance(definition[0], list):
                options = definition[0]
                if value not in options and not (isinstance(value, str) and value.startswith("{{")):
                    problems.append(f"{node_id}.{input_name} value {value!r} is unavailable")
    if problems:
        raise WorkflowError("Workflow is incompatible with ComfyUI: " + "; ".join(problems))


def load_workflow(path: str | Path) -> dict[str, Any]:
    """Load a JSON workflow object from disk.

    Raises:
        WorkflowError: If the file is missing, invalid JSON, or not an object.
    """
    try:
        workflow = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise WorkflowError(f"Unable to read workflow {path}: {error}") from error
    if not isinstance(workflow, dict):
        raise WorkflowError("Workflow must be a JSON object")
    return workflow


def apply_parameters(workflow: dict[str, Any], parameters: dict[str, Any]) -> dict[str, Any]:
    """Replace marked node inputs without mutating the loaded template.

    Args:
        workflow: API-format workflow node map.
        parameters: Marker names and replacement values.
    """
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


def prepare_workflow(workflow: dict[str, Any], parameters: dict[str, Any]) -> dict[str, Any]:
    """Validate and apply generic marker parameters to an API workflow.

    Raises:
        WorkflowError: If the workflow is not in API format.
    """
    validate_api_workflow(workflow)
    return apply_parameters(workflow, parameters)


def apply_generation_parameters(
    workflow: dict[str, Any],
    *,
    input_image: str | None = None,
    mask_image: str | None = None,
    positive_prompt: str | None = None,
    negative_prompt: str | None = None,
    checkpoint: str | None = None,
    vae: str | None = None,
    unet: str | None = None,
    clip_l: str | None = None,
    clip_t5: str | None = None,
    seed: int | None = None,
    width: int | None = None,
    height: int | None = None,
    steps: int | None = None,
    cfg: float | None = None,
    sampler: str | None = None,
    scheduler: str | None = None,
    denoise: float | None = None,
    loras: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Apply common image-generation settings without mutating the template.

    Args:
        workflow: API-format workflow node map.
        input_image: ComfyUI input filename, including subfolder when needed.
        mask_image: ComfyUI mask filename when the workflow has a mask input.
        positive_prompt: Text for the positive conditioning node.
        negative_prompt: Text for the negative conditioning node.
        checkpoint: ComfyUI checkpoint name, including nested model path.

    Raises:
        WorkflowError: If the workflow is malformed or required markers remain unresolved.
    """
    result = copy.deepcopy(workflow)
    validate_api_workflow(result)
    values = {
        "input_image": input_image,
        "prompt": positive_prompt,
        "negative_prompt": negative_prompt,
        "checkpoint": checkpoint,
        "vae": vae,
        "unet": unet,
        "clip_l": clip_l,
        "clip_t5": clip_t5,
        "seed": seed,
        "width": width,
        "height": height,
        "steps": steps,
        "cfg": cfg,
        "sampler": sampler,
        "scheduler": scheduler,
        "denoise": denoise,
    }
    result = apply_parameters(result, {key: value for key, value in values.items() if value is not None})

    for node in result.values():
        inputs = node["inputs"]
        class_type = node["class_type"]
        if class_type in {"CheckpointLoader", "CheckpointLoaderSimple"} and checkpoint is not None:
            inputs["ckpt_name"] = checkpoint
        if class_type == "LoadImage" and input_image is not None:
            inputs["image"] = input_image
        if class_type == "VAELoader" and vae is not None:
            inputs["vae_name"] = vae
        if class_type == "UNETLoader" and unet is not None:
            inputs["unet_name"] = unet
        if class_type == "DualCLIPLoader":
            if clip_l is not None:
                inputs["clip_name1"] = clip_l
            if clip_t5 is not None:
                inputs["clip_name2"] = clip_t5
        for key, value in {
            "seed": seed,
            "noise_seed": seed,
            "width": width,
            "height": height,
            "steps": steps,
            "cfg": cfg,
            "sampler_name": sampler,
            "scheduler": scheduler,
            "denoise": denoise,
        }.items():
            if key in inputs and value is not None:
                inputs[key] = value

    _apply_linked_prompts(result, positive_prompt, negative_prompt)
    if loras:
        apply_loras(result, loras)
    if mask_image is not None:
        result = apply_mask(result, mask_image)
    validate_resolved_workflow(result)
    return result


def apply_mask(workflow: dict[str, Any], mask_image: str) -> dict[str, Any]:
    """Inject a ``LoadImageMask`` node into every compatible mask input.

    Args:
        workflow: API-format workflow node map.
        mask_image: ComfyUI input filename for the mask image.

    Raises:
        WorkflowError: If the workflow has no input named ``mask``.
    """
    result = copy.deepcopy(workflow)
    target_nodes = [node for node in result.values() if "mask" in node["inputs"]]
    if not target_nodes:
        raise WorkflowError("Cannot apply a mask: workflow has no compatible mask input")

    numeric_ids = [int(node_id) for node_id in result if str(node_id).isdigit()]
    node_id = str(max(numeric_ids, default=0) + 1)
    result[node_id] = {
        "class_type": "LoadImageMask",
        "inputs": {
            "image": mask_image,
            "channel": "green",
            "upload": "image",
        },
    }
    for node in target_nodes:
        node["inputs"]["mask"] = [node_id, 0]
    return result


def apply_loras(workflow: dict[str, Any], loras: dict[str, float]) -> None:
    """Insert a LoRA loader chain and rewire checkpoint consumers in place.

    Args:
        workflow: Validated API-format workflow node map.
        loras: Mapping of ComfyUI LoRA names to model and CLIP strengths.

    Raises:
        WorkflowError: If the workflow has no checkpoint loader or a LoRA name is empty.
    """
    checkpoint_id = next(
        (
            node_id
            for node_id, node in workflow.items()
            if node["class_type"] in {"CheckpointLoader", "CheckpointLoaderSimple"}
        ),
        None,
    )
    if checkpoint_id is None:
        raise WorkflowError("Cannot apply LoRAs without a checkpoint loader")
    if any(not name for name in loras):
        raise WorkflowError("LoRA names must not be empty")

    consumers = []
    for node_id, node in workflow.items():
        if node_id == checkpoint_id:
            continue
        for input_name, value in node["inputs"].items():
            if isinstance(value, list) and len(value) == 2 and str(value[0]) == checkpoint_id:
                consumers.append((node, input_name, value[1]))

    numeric_ids = [int(node_id) for node_id in workflow if str(node_id).isdigit()]
    next_id = max(numeric_ids, default=0) + 1
    current_model = [checkpoint_id, 0]
    current_clip = [checkpoint_id, 1]
    for lora_name, strength in loras.items():
        node_id = str(next_id)
        workflow[node_id] = {
            "class_type": "LoraLoader",
            "inputs": {
                "lora_name": lora_name,
                "strength_model": strength,
                "strength_clip": strength,
                "model": current_model,
                "clip": current_clip,
            },
        }
        current_model = [node_id, 0]
        current_clip = [node_id, 1]
        next_id += 1

    for node, input_name, output_index in consumers:
        node["inputs"][input_name] = current_model if output_index == 0 else current_clip


def _apply_linked_prompts(
    workflow: dict[str, Any],
    positive_prompt: str | None,
    negative_prompt: str | None,
) -> None:
    for node in workflow.values():
        inputs = node["inputs"]
        if "positive" not in inputs or "negative" not in inputs:
            continue
        positive_id = _linked_node_id(inputs["positive"])
        negative_id = _linked_node_id(inputs["negative"])
        if positive_prompt is not None:
            _set_text_input(workflow, positive_id, positive_prompt)
        if negative_prompt is not None:
            _set_text_input(workflow, negative_id, negative_prompt)


def _linked_node_id(value: Any) -> str | None:
    if isinstance(value, list) and value:
        return str(value[0])
    return None


def _set_text_input(workflow: dict[str, Any], node_id: str | None, text: str) -> None:
    if node_id is None or node_id not in workflow:
        return
    inputs = workflow[node_id]["inputs"]
    if "text" in inputs:
        inputs["text"] = text