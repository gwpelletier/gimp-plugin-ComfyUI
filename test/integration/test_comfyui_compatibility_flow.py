import os
from pathlib import Path

import pytest

from comfyui_plugin.client import ComfyUIClient
from comfyui_plugin.workflow import load_workflow


pytestmark = pytest.mark.integration


@pytest.mark.skipif(not os.environ.get("COMFYUI_URL"), reason="Set COMFYUI_URL to run ComfyUI integration tests")
class TestComfyUICompatibilityFlow:
    def test_bundled_workflow_matches_live_node_and_resource_schema(self):
        # Arrange
        client = ComfyUIClient(os.environ["COMFYUI_URL"], timeout=10)
        workflow_paths = sorted(Path("workflows").glob("*-api.json"))

        # Act
        for workflow_path in workflow_paths:
            client.validate_workflow(load_workflow(workflow_path))
        stats = client.get_system_stats()

        # Assert
        assert len(workflow_paths) >= 6
        assert stats["system"]["comfyui_version"]
