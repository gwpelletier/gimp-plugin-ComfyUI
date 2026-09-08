import pytest

from comfyui_plugin.workflow import (
    WorkflowError,
    apply_generation_parameters,
    apply_loras,
    apply_mask,
    apply_parameters,
    load_workflow,
    prepare_workflow,
    validate_api_workflow,
    validate_resolved_workflow,
    validate_workflow_compatibility,
)


class TestValidateResolvedWorkflow:
    def test_allows_nodes_without_inputs(self):
        # Arrange
        workflow = {"1": {"class_type": "Note"}}

        # Act
        validate_resolved_workflow(workflow)

        # Assert
        assert workflow == {"1": {"class_type": "Note"}}

    def test_reports_all_unresolved_markers_with_input_paths(self):
        # Arrange
        workflow = {
            "1": {"inputs": {"text": "{{ prompt }}", "seed": 42}},
            "2": {"inputs": {"ckpt_name": "{{ checkpoint }}"}},
        }

        # Act / Assert
        with pytest.raises(
            WorkflowError,
            match=r"^Unresolved workflow parameters: 1\.text=\{\{ prompt \}\}, 2\.ckpt_name=\{\{ checkpoint \}\}$",
        ):
            validate_resolved_workflow(workflow)


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

    def test_accepts_linked_list_inputs(self):
        # Arrange
        workflow = {"1": {"class_type": "KSampler", "inputs": {"model": ["2", 0]}}}
        object_info = {"KSampler": {"input": {"required": {"model": ["MODEL"]}}}}

        # Act
        validate_workflow_compatibility(workflow, object_info)

        # Assert
        assert workflow["1"]["inputs"]["model"] == ["2", 0]

    def test_accepts_values_for_non_enumerated_inputs(self):
        # Arrange
        workflow = {"1": {"class_type": "KSampler", "inputs": {"seed": 42}}}
        object_info = {"KSampler": {"input": {"required": {"seed": ["INT", {"min": 0, "max": 100}]}}}}

        # Act
        validate_workflow_compatibility(workflow, object_info)

        # Assert
        assert workflow["1"]["inputs"]["seed"] == 42

    def test_resolves_flux_resources_in_bundled_workflow(self):
        # Arrange
        workflow = load_workflow("workflows/flux-image-edit-api.json")

        # Act
        resolved = apply_generation_parameters(
            workflow,
            input_image="uploads/source.png",
            positive_prompt="portrait",
            negative_prompt="blurry",
            unet="flux/flux1-dev-fp8-e4m3fn.safetensors",
            clip_l="flux/clip_l.safetensors",
            clip_t5="flux/t5xxl_fp8_e4m3fn.safetensors",
            vae="flux/ae.safetensors",
            seed=42,
            steps=20,
            cfg=3.5,
            sampler="euler",
            scheduler="normal",
            denoise=0.8,
        )

        # Assert
        assert resolved["1"]["inputs"]["unet_name"] == "flux/flux1-dev-fp8-e4m3fn.safetensors"
        assert resolved["2"]["inputs"]["clip_name2"] == "flux/t5xxl_fp8_e4m3fn.safetensors"
        assert all("{{" not in str(value) for node in resolved.values() for value in node["inputs"].values())

    def test_resolves_krea2_turbo_loader_resources(self):
        # Arrange
        workflow = {
            "1": {
                "class_type": "UNETLoader",
                "inputs": {"unet_name": "old-diffusion.safetensors"},
            },
            "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "old-clip.safetensors", "type": "krea2"}},
        }

        # Act
        resolved = apply_generation_parameters(
            workflow,
            diffusion_model="krea2-turbo.safetensors",
            krea_clip="krea2-text-encoder.safetensors",
        )

        # Assert
        assert resolved["1"]["inputs"]["unet_name"] == "krea2-turbo.safetensors"
        assert resolved["2"]["inputs"]["clip_name"] == "krea2-text-encoder.safetensors"
        assert workflow["1"]["inputs"]["unet_name"] == "old-diffusion.safetensors"


class TestApplyParameters:
    def test_apply_parameters_replaces_markers_without_mutating_template(self):
        # Arrange
        workflow = {"1": {"inputs": {"text": "{{ prompt }}", "steps": 20}}}

        # Act
        updated = apply_parameters(workflow, {"prompt": "portrait", "steps": 30})

        # Assert
        assert updated["1"]["inputs"] == {"text": "portrait", "steps": 20}
        assert workflow["1"]["inputs"]["text"] == "{{ prompt }}"

    def test_skips_malformed_nodes_and_non_dict_inputs(self):
        # Arrange
        workflow = {
            "1": "not-a-node",
            "2": {"class_type": "Note", "inputs": ["not", "a", "dict"]},
            "3": {"class_type": "Preview"},
            "4": {"inputs": {"text": "{{ prompt }}"}},
        }

        # Act
        updated = apply_parameters(workflow, {"prompt": "portrait"})

        # Assert
        assert updated == {
            "1": "not-a-node",
            "2": {"class_type": "Note", "inputs": ["not", "a", "dict"]},
            "3": {"class_type": "Preview"},
            "4": {"inputs": {"text": "portrait"}},
        }
        assert workflow["4"]["inputs"]["text"] == "{{ prompt }}"


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

    def test_rejects_non_object_json(self, tmp_path):
        # Arrange
        workflow_path = tmp_path / "list.json"
        workflow_path.write_text("[1, 2, 3]", encoding="utf-8")

        # Act
        with pytest.raises(WorkflowError, match="^Workflow must be a JSON object$"):
            load_workflow(workflow_path)

        # Assert
        assert workflow_path.exists()

    def test_loads_json_using_utf8(self, tmp_path):
        # Arrange
        workflow_path = tmp_path / "workflow.json"
        workflow_path.write_bytes(b'{"1": {"class_type": "Note", "inputs": {"text": "caf\xc3\xa9"}}}')

        # Act
        workflow = load_workflow(workflow_path)

        # Assert
        assert workflow["1"]["inputs"]["text"] == "caf\u00e9"


class TestValidateApiWorkflow:
    def test_rejects_node_missing_class_type(self):
        # Arrange
        workflow = {"1": {"inputs": {}}}

        # Act
        with pytest.raises(WorkflowError, match="missing class_type"):
            validate_api_workflow(workflow)

        # Assert
        assert workflow == {"1": {"inputs": {}}}

    def test_rejects_node_missing_inputs(self):
        # Arrange
        workflow = {"1": {"class_type": "KSampler"}}

        # Act
        with pytest.raises(WorkflowError, match="missing inputs"):
            validate_api_workflow(workflow)

        # Assert
        assert workflow == {"1": {"class_type": "KSampler"}}


class TestPrepareWorkflow:
    def test_applies_parameters_without_mutating_template(self):
        # Arrange
        workflow = {"1": {"class_type": "CLIPTextEncode", "inputs": {"text": "{{ prompt }}"}}}

        # Act
        prepared = prepare_workflow(workflow, {"prompt": "portrait"})

        # Assert
        assert prepared["1"]["inputs"]["text"] == "portrait"
        assert workflow["1"]["inputs"]["text"] == "{{ prompt }}"

    def test_rejects_ui_workflow_format(self):
        # Arrange
        workflow = {"nodes": [], "links": []}

        # Act
        with pytest.raises(WorkflowError, match="API format"):
            prepare_workflow(workflow, {"prompt": "portrait"})

        # Assert
        assert workflow == {"nodes": [], "links": []}


class TestApplyGenerationParameters:
    def test_applies_markers_loader_resources_and_sampler_fields_without_mutating_template(self):
        # Arrange
        workflow = {
            "1": {"class_type": "CheckpointLoader", "inputs": {"ckpt_name": "old-checkpoint.safetensors"}},
            "2": {"class_type": "LoadImage", "inputs": {"image": "old-input.png"}},
            "3": {"class_type": "VAELoader", "inputs": {"vae_name": "old-vae.safetensors"}},
            "4": {"class_type": "UNETLoader", "inputs": {"unet_name": "old-unet.safetensors"}},
            "5": {"class_type": "DiffusionModelLoader", "inputs": {"model_name": "old-diffusion.safetensors"}},
            "6": {"class_type": "CLIPLoader", "inputs": {"clip_name": "old-krea-clip.safetensors"}},
            "7": {
                "class_type": "DualCLIPLoader",
                "inputs": {"clip_name1": "old-clip-l.safetensors", "clip_name2": "old-clip-t5.safetensors"},
            },
            "8": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": 1,
                    "noise_seed": 2,
                    "width": 256,
                    "height": 256,
                    "steps": 10,
                    "cfg": 4.0,
                    "sampler_name": "old-sampler",
                    "scheduler": "old-scheduler",
                    "denoise": 0.1,
                },
            },
            "9": {
                "class_type": "ParameterEcho",
                "inputs": {
                    "image": "{{ input_image }}",
                    "positive": "{{ prompt }}",
                    "negative": "{{ negative_prompt }}",
                    "checkpoint": "{{ checkpoint }}",
                    "vae": "{{ vae }}",
                    "unet": "{{ unet }}",
                    "clip_l": "{{ clip_l }}",
                    "clip_t5": "{{ clip_t5 }}",
                    "diffusion": "{{ diffusion_model }}",
                    "krea_clip": "{{ krea_clip }}",
                    "seed": "{{ seed }}",
                    "width": "{{ width }}",
                    "height": "{{ height }}",
                    "steps": "{{ steps }}",
                    "cfg": "{{ cfg }}",
                    "sampler": "{{ sampler }}",
                    "scheduler": "{{ scheduler }}",
                    "denoise": "{{ denoise }}",
                },
            },
        }

        # Act
        updated = apply_generation_parameters(
            workflow,
            input_image="uploads/source.png",
            positive_prompt="new positive",
            negative_prompt="new negative",
            checkpoint="models/checkpoint.safetensors",
            vae="models/vae.safetensors",
            unet="models/unet.safetensors",
            clip_l="models/clip-l.safetensors",
            clip_t5="models/clip-t5.safetensors",
            diffusion_model="models/diffusion.safetensors",
            krea_clip="models/krea-clip.safetensors",
            seed=42,
            width=1024,
            height=768,
            steps=30,
            cfg=6.5,
            sampler="euler",
            scheduler="normal",
            denoise=0.65,
        )

        # Assert
        assert updated["1"]["inputs"]["ckpt_name"] == "models/checkpoint.safetensors"
        assert updated["2"]["inputs"]["image"] == "uploads/source.png"
        assert updated["3"]["inputs"]["vae_name"] == "models/vae.safetensors"
        assert updated["4"]["inputs"]["unet_name"] == "models/diffusion.safetensors"
        assert updated["5"]["inputs"]["model_name"] == "models/diffusion.safetensors"
        assert updated["6"]["inputs"]["clip_name"] == "models/krea-clip.safetensors"
        assert updated["7"]["inputs"] == {
            "clip_name1": "models/clip-l.safetensors",
            "clip_name2": "models/clip-t5.safetensors",
        }
        assert updated["8"]["inputs"] == {
            "seed": 42,
            "noise_seed": 42,
            "width": 1024,
            "height": 768,
            "steps": 30,
            "cfg": 6.5,
            "sampler_name": "euler",
            "scheduler": "normal",
            "denoise": 0.65,
        }
        assert updated["9"]["inputs"] == {
            "image": "uploads/source.png",
            "positive": "new positive",
            "negative": "new negative",
            "checkpoint": "models/checkpoint.safetensors",
            "vae": "models/vae.safetensors",
            "unet": "models/unet.safetensors",
            "clip_l": "models/clip-l.safetensors",
            "clip_t5": "models/clip-t5.safetensors",
            "diffusion": "models/diffusion.safetensors",
            "krea_clip": "models/krea-clip.safetensors",
            "seed": 42,
            "width": 1024,
            "height": 768,
            "steps": 30,
            "cfg": 6.5,
            "sampler": "euler",
            "scheduler": "normal",
            "denoise": 0.65,
        }
        assert workflow["1"]["inputs"]["ckpt_name"] == "old-checkpoint.safetensors"
        assert workflow["9"]["inputs"]["positive"] == "{{ prompt }}"

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

    def test_updates_only_clip_name1_when_clip_t5_omitted(self):
        # Arrange
        workflow = {
            "1": {
                "class_type": "DualCLIPLoader",
                "inputs": {"clip_name1": "old_l.safetensors", "clip_name2": "old_t5.safetensors"},
            }
        }

        # Act
        updated = apply_generation_parameters(workflow, clip_l="new_l.safetensors")

        # Assert
        assert updated["1"]["inputs"]["clip_name1"] == "new_l.safetensors"
        assert updated["1"]["inputs"]["clip_name2"] == "old_t5.safetensors"

    def test_updates_only_clip_name2_when_clip_l_omitted(self):
        # Arrange
        workflow = {
            "1": {
                "class_type": "DualCLIPLoader",
                "inputs": {"clip_name1": "old_l.safetensors", "clip_name2": "old_t5.safetensors"},
            }
        }

        # Act
        updated = apply_generation_parameters(workflow, clip_t5="new_t5.safetensors")

        # Assert
        assert updated["1"]["inputs"]["clip_name1"] == "old_l.safetensors"
        assert updated["1"]["inputs"]["clip_name2"] == "new_t5.safetensors"

    def test_applies_loras_and_rewires_consumers(self):
        # Arrange
        workflow = {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "old.safetensors"}},
            "2": {"class_type": "KSampler", "inputs": {"model": ["1", 0]}},
        }

        # Act
        updated = apply_generation_parameters(
            workflow,
            checkpoint="new.safetensors",
            loras={"style.safetensors": 0.5},
        )

        # Assert
        assert updated["1"]["inputs"]["ckpt_name"] == "new.safetensors"
        assert updated["3"] == {
            "class_type": "LoraLoader",
            "inputs": {
                "lora_name": "style.safetensors",
                "strength_model": 0.5,
                "strength_clip": 0.5,
                "model": ["1", 0],
                "clip": ["1", 1],
            },
        }
        assert updated["2"]["inputs"]["model"] == ["3", 0]
        assert "3" not in workflow

    def test_leaves_positive_text_when_only_negative_prompt_provided(self):
        # Arrange
        workflow = {
            "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "old positive"}},
            "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "old negative"}},
            "4": {"class_type": "KSampler", "inputs": {"positive": ["2", 0], "negative": ["3", 0]}},
        }

        # Act
        updated = apply_generation_parameters(workflow, negative_prompt="new negative")

        # Assert
        assert updated["2"]["inputs"]["text"] == "old positive"
        assert updated["3"]["inputs"]["text"] == "new negative"

    def test_leaves_negative_text_when_only_positive_prompt_provided(self):
        # Arrange
        workflow = {
            "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "old positive"}},
            "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "old negative"}},
            "4": {"class_type": "KSampler", "inputs": {"positive": ["2", 0], "negative": ["3", 0]}},
        }

        # Act
        updated = apply_generation_parameters(workflow, positive_prompt="new positive")

        # Assert
        assert updated["2"]["inputs"]["text"] == "new positive"
        assert updated["3"]["inputs"]["text"] == "old negative"

    def test_ignores_non_list_prompt_links(self):
        # Arrange
        workflow = {
            "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "old positive"}},
            "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "old negative"}},
            "4": {"class_type": "KSampler", "inputs": {"positive": "2-disabled", "negative": ["3", 0]}},
        }

        # Act
        updated = apply_generation_parameters(
            workflow,
            positive_prompt="new positive",
            negative_prompt="new negative",
        )

        # Assert
        assert updated["2"]["inputs"]["text"] == "old positive"
        assert updated["3"]["inputs"]["text"] == "new negative"

    def test_ignores_incomplete_prompt_link_pairs(self):
        # Arrange
        workflow = {
            "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "old incomplete positive"}},
            "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "old complete positive"}},
            "4": {"class_type": "CLIPTextEncode", "inputs": {"text": "old complete negative"}},
            "5": {"class_type": "KSampler", "inputs": {"positive": ["2", 0]}},
            "6": {"class_type": "KSampler", "inputs": {"positive": ["3", 0], "negative": ["4", 0]}},
        }

        # Act
        updated = apply_generation_parameters(
            workflow,
            positive_prompt="new positive",
            negative_prompt="new negative",
        )

        # Assert
        assert updated["2"]["inputs"]["text"] == "old incomplete positive"
        assert updated["3"]["inputs"]["text"] == "new positive"
        assert updated["4"]["inputs"]["text"] == "new negative"

    def test_ignores_prompt_links_to_missing_nodes(self):
        # Arrange
        workflow = {
            "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "old positive"}},
            "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "old negative"}},
            "4": {"class_type": "KSampler", "inputs": {"positive": ["99", 0], "negative": ["3", 0]}},
        }

        # Act
        updated = apply_generation_parameters(
            workflow,
            positive_prompt="new positive",
            negative_prompt="new negative",
        )

        # Assert
        assert updated["3"]["inputs"]["text"] == "new negative"
        assert set(updated) == {"2", "3", "4"}


class TestApplyLoras:
    def test_inserts_multiple_loras_after_checkpoint_loader_and_rewires_final_outputs(self):
        # Arrange
        workflow = {
            "1": {"class_type": "CheckpointLoader", "inputs": {"ckpt_name": "model.safetensors"}},
            "2": {"class_type": "KSampler", "inputs": {"model": ["1", 0], "positive": ["1", 1]}},
        }

        # Act
        apply_loras(workflow, {"style.safetensors": 0.75, "detail.safetensors": 0.25})

        # Assert
        assert workflow["3"] == {
            "class_type": "LoraLoader",
            "inputs": {
                "lora_name": "style.safetensors",
                "strength_model": 0.75,
                "strength_clip": 0.75,
                "model": ["1", 0],
                "clip": ["1", 1],
            },
        }
        assert workflow["4"] == {
            "class_type": "LoraLoader",
            "inputs": {
                "lora_name": "detail.safetensors",
                "strength_model": 0.25,
                "strength_clip": 0.25,
                "model": ["3", 0],
                "clip": ["3", 1],
            },
        }
        assert workflow["2"]["inputs"]["model"] == ["4", 0]
        assert workflow["2"]["inputs"]["positive"] == ["4", 1]

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
        with pytest.raises(WorkflowError, match="^Cannot apply LoRAs without a checkpoint loader$"):
            apply_loras(workflow, {"style.safetensors": 0.75})

        # Assert
        assert list(workflow) == ["1"]

    def test_rejects_empty_lora_name(self):
        # Arrange
        workflow = {"1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "model.safetensors"}}}

        # Act
        with pytest.raises(WorkflowError, match="^LoRA names must not be empty$"):
            apply_loras(workflow, {"": 0.5})

        # Assert
        assert list(workflow) == ["1"]

    def test_leaves_unrelated_links_and_scalar_inputs_untouched(self):
        # Arrange
        workflow = {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "model.safetensors"}},
            "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "portrait", "clip": ["1", 1]}},
            "3": {"class_type": "KSampler", "inputs": {"model": ["1", 0], "positive": ["2", 0], "seed": 7}},
        }

        # Act
        apply_loras(workflow, {"style.safetensors": 1.0})

        # Assert
        assert workflow["4"]["class_type"] == "LoraLoader"
        assert workflow["2"]["inputs"]["clip"] == ["4", 1]
        assert workflow["3"]["inputs"]["model"] == ["4", 0]
        assert workflow["3"]["inputs"]["positive"] == ["2", 0]
        assert workflow["3"]["inputs"]["seed"] == 7


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

    def test_uses_first_numeric_node_id_when_workflow_has_only_named_nodes(self):
        # Arrange
        workflow = {"mask-target": {"class_type": "VAEEncodeForInpaint", "inputs": {"mask": "old-mask"}}}

        # Act
        updated = apply_mask(workflow, "uploads/mask.png")

        # Assert
        assert updated["1"] == {
            "class_type": "LoadImageMask",
            "inputs": {"image": "uploads/mask.png", "channel": "green", "upload": "image"},
        }
        assert updated["mask-target"]["inputs"]["mask"] == ["1", 0]

    def test_bundled_inpainting_workflow_is_mask_compatible(self):
        # Arrange
        workflow = load_workflow("workflows/sdxl-inpainting-api.json")

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
        assert updated["5"]["inputs"]["mask"] == ["9", 0]
        assert updated["9"] == {
            "class_type": "LoadImageMask",
            "inputs": {"image": "uploads/mask.png", "channel": "green", "upload": "image"},
        }