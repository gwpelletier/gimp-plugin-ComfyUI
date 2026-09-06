import os

import pytest

from comfyui_plugin.client import ComfyUIClient


pytestmark = pytest.mark.integration


@pytest.mark.skipif(not os.environ.get("COMFYUI_URL"), reason="Set COMFYUI_URL to run ComfyUI integration tests")
class TestComfyUIKreaFlow:
    def test_reports_krea_models_as_hosted_custom_node_resources(self):
        # Arrange
        client = ComfyUIClient(os.environ["COMFYUI_URL"], timeout=10)

        # Act
        models = client.get_available_krea_models()

        # Assert
        assert models
        assert any(model.startswith("Krea 2") for model in models)