from comfyui_plugin.resources import filter_options, workflow_supports_vae


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