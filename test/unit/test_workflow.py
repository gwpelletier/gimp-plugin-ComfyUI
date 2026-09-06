import pytest

from comfyui_plugin.workflow import (
    WorkflowError,
    apply_generation_parameters,
    apply_loras,
    apply_mask,
    apply_parameters,
    load_workflow,
    validate_workflow_compatibility,
)


class TestValidateWorkflowCompatibility:
    def test_rejects_missing_node_from_object_info(self):
        # Arrange
        workflow = {"1": {"class_type": "CustomNode", "inputs": {}}}

        # Act
        with pytest.raises(WorkflowError, match="unavailable node"):
            validate_workflow_compatibility(workflow, {})

        # Assert
        assert workflow["1"]["class_type"] == "CustomNode"

    def test_rejects_unsupported_input_and_resource_value(self):
        # Arrange
        workflow = {
            "1": {
                "class_type": "KSampler",
                "inputs": {"sampler_name": "missing", "unknown": 1},
            }
        }
        object_info = {
            "KSampler": {
                "input": {"required": {"sampler_name": [["euler"]]}, "optional": {}}
            }
        }

        # Act
        with pytest.raises(WorkflowError, match="unsupported|unavailable"):
            validate_workflow_compatibility(workflow, object_info)

        # Assert
        assert workflow["1"]["inputs"]["sampler_name"] == "missing"

    def test_accepts_legacy_image_upload_hint(self):
        # Arrange
        workflow = {"1": {"class_type": "LoadImage", "inputs": {"image": "input.png", "upload": "image"}}}
        object_info = {"LoadImage": {"input": {"required": {"image": [["input.png"]]}}}}

        # Act
        validate_workflow_compatibility(workflow, object_info)

        # Assert
        assert workflow["1"]["inputs"]["upload"] == "image"


class TestApplyParameters:
    def test_apply_parameters_replaces_markers_without_mutating_template(self):
        # Arrange
        workflow = {"1": {"inputs": {"text": "{{ prompt }}", "steps": 20}}}

        # Act
        updated = apply_parameters(workflow, {"prompt": "portrait", "steps": 30})

        # Assert
        assert updated["1"]["inputs"] == {"text": "portrait", "steps": 20}
        assert workflow["1"]["inputs"]["text"] == "{{ prompt }}"


class TestLoadWorkflow:
    def test_rejects_missing_file(self, tmp_path):
        # Arrange
        missing_path = tmp_path / "missing.json"

        # Act
        with pytest.raises(WorkflowError, match="Unable to read workflow"):
            load_workflow(missing_path)

        # Assert
        assert not missing_path.exists()

    def test_rejects_malformed_json(self, tmp_path):
        # Arrange
        workflow_path = tmp_path / "broken.json"
        workflow_path.write_text("{not json", encoding="utf-8")

        # Act
        with pytest.raises(WorkflowError, match="Unable to read workflow"):
            load_workflow(workflow_path)

        # Assert
        assert workflow_path.exists()


class TestApplyGenerationParameters:
    def test_updates_linked_prompts_and_preserves_checkpoint_path(self):
        # Arrange
        workflow = {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "old.safetensors"}},
            "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "old positive"}},
            "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "old negative"}},
            "4": {
                "class_type": "KSampler",
                "inputs": {
                    "positive": ["2", 0],
                    "negative": ["3", 0],
                    "seed": 1,
                    "steps": 10,
                },
            },
        }

        # Act
        updated = apply_generation_parameters(
            workflow,
            checkpoint="subfolder/model.safetensors",
            positive_prompt="new positive",
            negative_prompt="new negative",
            seed=42,
            steps=25,
        )

        # Assert
        assert updated["1"]["inputs"]["ckpt_name"] == "subfolder/model.safetensors"
        assert updated["2"]["inputs"]["text"] == "new positive"
        assert updated["3"]["inputs"]["text"] == "new negative"
        assert updated["4"]["inputs"] == {
            "positive": ["2", 0],
            "negative": ["3", 0],
            "seed": 42,
            "steps": 25,
        }

    def test_rejects_ui_workflow_format(self):
        # Arrange
        workflow = {"nodes": [], "links": []}

        # Act
        with pytest.raises(WorkflowError, match="API format"):
            apply_generation_parameters(workflow)

        # Assert
        assert workflow == {"nodes": [], "links": []}

    def test_rejects_unresolved_markers(self):
        # Arrange
        workflow = {"1": {"class_type": "LoadImage", "inputs": {"image": "{{input_image}}"}}}

        # Act
        with pytest.raises(WorkflowError, match="Unresolved workflow parameters"):
            apply_generation_parameters(workflow)

        # Assert
        assert workflow["1"]["inputs"]["image"] == "{{input_image}}"


class TestApplyLoras:
    def test_inserts_lora_chain_and_rewires_model_and_clip_consumers(self):
        # Arrange
        workflow = {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "model.safetensors"}},
            "2": {"class_type": "KSampler", "inputs": {"model": ["1", 0], "positive": ["1", 1]}},
        }

        # Act
        apply_loras(workflow, {"style.safetensors": 0.75})

        # Assert
        assert workflow["3"]["class_type"] == "LoraLoader"
        assert workflow["3"]["inputs"]["model"] == ["1", 0]
        assert workflow["2"]["inputs"]["model"] == ["3", 0]
        assert workflow["2"]["inputs"]["positive"] == ["3", 1]

    def test_rejects_loras_without_checkpoint_loader(self):
        # Arrange
        workflow = {"1": {"class_type": "KSampler", "inputs": {}}}

        # Act
        with pytest.raises(WorkflowError, match="checkpoint loader"):
            apply_loras(workflow, {"style.safetensors": 0.75})

        # Assert
        assert list(workflow) == ["1"]


class TestApplyMask:
    def test_injects_mask_loader_into_all_mask_consumers(self):
        # Arrange
        workflow = {
            "1": {"class_type": "LoadImage", "inputs": {"image": "input.png"}},
            "2": {"class_type": "VAEEncodeForInpaint", "inputs": {"mask": "old-mask"}},
            "3": {"class_type": "SetLatentNoiseMask", "inputs": {"mask": "old-mask"}},
        }

        # Act
        updated = apply_mask(workflow, "uploads/mask.png")

        # Assert
        assert updated["4"] == {
            "class_type": "LoadImageMask",
            "inputs": {"image": "uploads/mask.png", "channel": "green", "upload": "image"},
        }
        assert updated["2"]["inputs"]["mask"] == ["4", 0]
        assert updated["3"]["inputs"]["mask"] == ["4", 0]

    def test_rejects_workflow_without_mask_consumers(self):
        # Arrange
        workflow = {"1": {"class_type": "KSampler", "inputs": {"model": ["2", 0]}}}

        # Act
        with pytest.raises(WorkflowError, match="no compatible mask input"):
            apply_mask(workflow, "mask.png")

        # Assert
        assert workflow["1"]["inputs"] == {"model": ["2", 0]}

    def test_does_not_mutate_template(self):
        # Arrange
        workflow = {"1": {"class_type": "VAEEncodeForInpaint", "inputs": {"mask": "old-mask"}}}

        # Act
        updated = apply_mask(workflow, "mask.png")

        # Assert
        assert workflow["1"]["inputs"]["mask"] == "old-mask"
        assert updated["1"]["inputs"]["mask"] == ["2", 0]

    def test_bundled_inpainting_workflow_is_mask_compatible(self):
        # Arrange
        workflow = load_workflow("workflows/inpainting-api.json")

        # Act
        updated = apply_generation_parameters(
            workflow,
            input_image="uploads/source.png",
            mask_image="uploads/mask.png",
            positive_prompt="restore the selected area",
            negative_prompt="blurry",
            checkpoint="models/checkpoint.safetensors",
            seed=42,
            steps=6,
            cfg=7,
            sampler="euler",
            scheduler="normal",
            denoise=0.65,
        )

        # Assert
        assert updated["6"]["inputs"]["mask"] == ["10", 0]
        assert updated["10"] == {
            "class_type": "LoadImageMask",
            "inputs": {"image": "uploads/mask.png", "channel": "green", "upload": "image"},
        }