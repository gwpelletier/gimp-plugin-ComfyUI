import os

import pytest

from comfyui_plugin.client import ComfyUIClient
from comfyui_plugin.workflow import load_workflow


pytestmark = pytest.mark.integration


@pytest.mark.skipif(not os.environ.get("COMFYUI_URL"), reason="Set COMFYUI_URL to run ComfyUI integration tests")
class TestComfyUICompatibilityFlow:
    def test_bundled_workflow_matches_live_node_and_resource_schema(self):
        # Arrange
        client = ComfyUIClient(os.environ["COMFYUI_URL"], timeout=10)
        workflow = load_workflow("workflows/image-edit-api.json")

        # Act
        client.validate_workflow(workflow)
        stats = client.get_system_stats()

        # Assert
        assert stats["system"]["comfyui_version"]
