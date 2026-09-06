import os

import pytest

from comfyui_plugin.client import ComfyUIClient


pytestmark = pytest.mark.integration


@pytest.mark.skipif(not os.environ.get("COMFYUI_URL"), reason="Set COMFYUI_URL to run ComfyUI integration tests")
class TestComfyUIResourceFlow:
    def test_object_info_resources_are_read_without_losing_nested_paths(self):
        # Arrange
        client = ComfyUIClient(os.environ["COMFYUI_URL"], timeout=10)

        # Act
        checkpoints = client.get_available_checkpoints()
        loras = client.get_available_loras()
        vaes = client.get_available_vaes()

        # Assert
        assert all(isinstance(value, str) and value for value in checkpoints)
        assert all(isinstance(value, str) and value for value in loras)
        assert all(isinstance(value, str) and value for value in vaes)
