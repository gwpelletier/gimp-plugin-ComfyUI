import os

import pytest

from comfyui_plugin.client import ComfyUIClient


pytestmark = pytest.mark.integration


@pytest.mark.skipif(not os.environ.get("COMFYUI_URL"), reason="Set COMFYUI_URL to run ComfyUI integration tests")
class TestComfyUIWebSocketFlow:
    def test_connects_and_closes_standard_library_websocket(self):
        # Arrange
        client = ComfyUIClient(os.environ["COMFYUI_URL"], timeout=10)
        websocket = client.open_websocket()

        # Act
        websocket.connect()
        websocket.close()

        # Assert
        assert websocket._socket is None
