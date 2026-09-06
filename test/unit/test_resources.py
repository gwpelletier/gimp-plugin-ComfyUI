import pytest

from comfyui_plugin.resources import (
    CheckpointType,
    checkpoint_profile,
    filter_options,
    infer_checkpoint_type,
    validate_checkpoint_workflow,
    workflow_supports_vae,
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


class TestCheckpointProfiles:
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