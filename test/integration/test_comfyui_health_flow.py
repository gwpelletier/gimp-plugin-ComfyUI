import os

import pytest

from comfyui_plugin.client import ComfyUIClient


pytestmark = pytest.mark.integration


class TestComfyUIHealthFlow:
    @pytest.mark.skipif(not os.environ.get("COMFYUI_URL"), reason="Set COMFYUI_URL to run ComfyUI integration tests")
    def test_comfyui_health_endpoint_responds(self):
        # Arrange
        client = ComfyUIClient(os.environ["COMFYUI_URL"])

        # Act
        is_healthy = client.health_check()

        # Assert
        assert is_healthy, "ComfyUI did not respond to /system_stats"