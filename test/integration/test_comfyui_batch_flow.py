import os
from pathlib import Path

import pytest

from comfyui_plugin.client import ComfyUIClient
from comfyui_plugin.generation import GenerationCoordinator, GenerationRequest
from comfyui_plugin.workflow import load_workflow


pytestmark = pytest.mark.integration


def _required_environment():
    names = ("COMFYUI_URL", "COMFYUI_TEST_IMAGE", "COMFYUI_TEST_IMAGE_2", "COMFYUI_CHECKPOINT")
    return [name for name in names if not os.environ.get(name)]


@pytest.mark.skipif(
    _required_environment(),
    reason="Set COMFYUI_URL, COMFYUI_TEST_IMAGE, COMFYUI_TEST_IMAGE_2, and COMFYUI_CHECKPOINT",
)
class TestComfyUIBatchFlow:
    def test_processes_two_inputs_and_returns_two_outputs(self):
        # Arrange
        client = ComfyUIClient(os.environ["COMFYUI_URL"], timeout=60)
        workflow = load_workflow("workflows/image-edit-api.json")
        requests = []
        for index, environment_name in enumerate(("COMFYUI_TEST_IMAGE", "COMFYUI_TEST_IMAGE_2")):
            upload = client.upload_image(Path(os.environ[environment_name]), subfolder="gimp-comfyui-batch")
            input_name = "/".join(part for part in (upload.subfolder, upload.filename) if part)
            requests.append(
                GenerationRequest(
                    workflow=workflow,
                    prompt=f"batch test input {index}",
                    negative_prompt="blurry, distorted, low quality",
                    checkpoint=os.environ["COMFYUI_CHECKPOINT"],
                    input_image=input_name,
                    seed=20260905 + index,
                    steps=int(os.environ.get("COMFYUI_TEST_STEPS", "6")),
                )
            )

        # Act
        summary = GenerationCoordinator(client).run_batch(requests)

        # Assert
        assert len(summary.completed) == 2
        assert all(item.result.images for item in summary.completed)
