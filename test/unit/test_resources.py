import pytest

from comfyui_plugin.resources import (
    best_guess_option,
    CheckpointType,
    checkpoint_profile,
    filter_options,
    infer_checkpoint_type,
    validate_checkpoint_workflow,
    workflow_supports_vae,
    workflow_matches_checkpoint_type,
    workflow_supports_inpainting,
    family_supports_mode,
)


class TestFilterOptions:
    def test_filters_case_insensitively_and_preserves_server_order(self):
        # Arrange
        options = ["sdxl/base.safetensors", "SDXL/refiner.safetensors", "flux/dev"]

        # Act
        filtered = filter_options(options, "ref")

        # Assert
        assert filtered == ["SDXL/refiner.safetensors"]

    def test_empty_query_returns_all_options(self):
        # Arrange
        options = ["nested/model.safetensors"]

        # Act
        filtered = filter_options(options, " ")

        # Assert
        assert filtered == options

    def test_best_guess_preserves_current_or_matches_hints(self):
        # Arrange
        options = ["text_encoders/t5xxl.safetensors", "text_encoders/clip_l.safetensors"]

        # Act
        current = best_guess_option(options, ("clip_l",), "text_encoders/clip_l.safetensors")
        guessed = best_guess_option(options, ("t5",))

        # Assert
        assert current == "text_encoders/clip_l.safetensors"
        assert guessed == "text_encoders/t5xxl.safetensors"


class TestWorkflowSupportsVae:
    def test_detects_explicit_vae_loader(self):
        # Arrange
        workflow = {"1": {"class_type": "VAELoader", "inputs": {"vae_name": "default.vae"}}}

        # Act
        supported = workflow_supports_vae(workflow)

        # Assert
        assert supported

    def test_rejects_workflow_without_vae_input(self):
        # Arrange
        workflow = {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}}

        # Act
        supported = workflow_supports_vae(workflow)

        # Assert
        assert not supported


class TestWorkflowSupportsInpainting:
    def test_detects_mask_input(self):
        # Arrange
        workflow = {"1": {"class_type": "VAEEncodeForInpaint", "inputs": {"mask": ["2", 0]}}}

        # Act
        supported = workflow_supports_inpainting(workflow)

        # Assert
        assert supported

    def test_rejects_text_to_image_workflow(self):
        # Arrange
        workflow = {"1": {"class_type": "Krea2ImageNode", "inputs": {"prompt": "portrait"}}}

        # Act
        supported = workflow_supports_inpainting(workflow)

        # Assert
        assert not supported


class TestFamilySupportsMode:
    def test_rejects_krea2_turbo_for_inpainting(self):
        # Arrange
        family = CheckpointType.KREA2_TURBO

        # Act
        supported = family_supports_mode(family, "Inpainting")

        # Assert
        assert not supported


class TestCheckpointProfiles:
    def test_infers_krea2_from_workflow_node(self):
        # Arrange
        workflow = {
            "1": {"class_type": "UNETLoader", "inputs": {}},
            "2": {"class_type": "CLIPLoader", "inputs": {"type": "krea2"}},
            "3": {"class_type": "VAELoader", "inputs": {}},
        }

        # Act
        checkpoint_type = infer_checkpoint_type(workflow)

        # Assert
        assert checkpoint_type == CheckpointType.KREA2_TURBO

    def test_infers_sd15_from_classic_checkpoint_workflow(self):
        # Arrange
        workflow = {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {}},
            "2": {"class_type": "CLIPTextEncode", "inputs": {}},
        }

        # Act
        checkpoint_type = infer_checkpoint_type(workflow)

        # Assert
        assert checkpoint_type == CheckpointType.SD15

    def test_matches_only_selected_workflow_family(self):
        # Arrange
        flux_workflow = {
            "1": {"class_type": "UNETLoader", "inputs": {}},
            "2": {"class_type": "DualCLIPLoader", "inputs": {}},
        }

        # Act
        matches = workflow_matches_checkpoint_type(flux_workflow, CheckpointType.FLUX)
        misses = workflow_matches_checkpoint_type(flux_workflow, CheckpointType.SDXL)

        # Assert
        assert matches
        assert not misses

    def test_workflow_structure_takes_precedence_over_checkpoint_name(self):
        # Arrange
        workflow = {
            "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "flux-dev.safetensors"}},
            "2": {"class_type": "DualCLIPLoader", "inputs": {}},
        }

        # Act
        checkpoint_type = infer_checkpoint_type(workflow, "sdxl/base.safetensors")

        # Assert
        assert checkpoint_type == CheckpointType.FLUX

    def test_checkpoint_name_provides_lower_confidence_hint(self):
        # Arrange
        workflow = {"1": {"class_type": "CheckpointLoaderSimple", "inputs": {}}}

        # Act
        profile = checkpoint_profile(workflow, "models/sdxl/base.safetensors")

        # Assert
        assert profile.checkpoint_type == CheckpointType.SDXL
        assert profile.confidence == "medium"

    def test_explicit_override_wins_over_inference(self):
        # Arrange
        workflow = {"1": {"class_type": "UNETLoader", "inputs": {}}}

        # Act
        profile = checkpoint_profile(workflow, override=CheckpointType.SDXL)

        # Assert
        assert profile.checkpoint_type == CheckpointType.SDXL
        assert profile.confidence == "high"
        assert profile.denoise == 0.8

    def test_rejects_flux_checkpoint_with_classic_workflow(self):
        # Arrange
        workflow = {"1": {"class_type": "CheckpointLoaderSimple", "inputs": {}}}

        # Act
        with pytest.raises(ValueError, match="UNETLoader and DualCLIPLoader"):
            validate_checkpoint_workflow(CheckpointType.FLUX, workflow)

    def test_rejects_krea2_checkpoint_without_krea_node(self):
        # Arrange
        workflow = {"1": {"class_type": "CheckpointLoaderSimple", "inputs": {}}}

        # Act and Assert
        with pytest.raises(ValueError, match="Diffusion Model, Krea2 CLIP, and VAE"):
            validate_checkpoint_workflow(CheckpointType.KREA2_TURBO, workflow)