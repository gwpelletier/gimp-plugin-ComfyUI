import os
from pathlib import Path

import pytest

from comfyui_plugin.client import ComfyUIClient, ComfyUIEventType
from comfyui_plugin.generation import GenerationCoordinator, GenerationRequest
from comfyui_plugin.workflow import load_workflow


pytestmark = pytest.mark.integration


def _required_environment():
    names = ("COMFYUI_URL", "COMFYUI_TEST_IMAGE", "COMFYUI_CHECKPOINT")
    missing = [name for name in names if not os.environ.get(name)]
    return missing


@pytest.mark.skipif(_required_environment(), reason="Set COMFYUI_URL, COMFYUI_TEST_IMAGE, and COMFYUI_CHECKPOINT")
class TestComfyUIGenerationFlow:
    def test_upload_queue_and_retrieve_generated_image(self):
        # Arrange
        client = ComfyUIClient(os.environ["COMFYUI_URL"], timeout=60)
        input_path = Path(os.environ["COMFYUI_TEST_IMAGE"])
        upload = client.upload_image(input_path, subfolder="gimp-comfyui-test")
        workflow = load_workflow("workflows/image-edit-api.json")
        input_name = "/".join(part for part in (upload.subfolder, upload.filename) if part)
        request = GenerationRequest(
            workflow=workflow,
            prompt=os.environ.get("COMFYUI_TEST_PROMPT", "a crisp studio portrait with soft natural light"),
            negative_prompt=os.environ.get("COMFYUI_TEST_NEGATIVE_PROMPT", "blurry, distorted, low quality"),
            checkpoint=os.environ["COMFYUI_CHECKPOINT"],
            input_image=input_name,
            seed=int(os.environ.get("COMFYUI_TEST_SEED", "20260905")),
            steps=int(os.environ.get("COMFYUI_TEST_STEPS", "6")),
            cfg=float(os.environ.get("COMFYUI_TEST_CFG", "7")),
            sampler=os.environ.get("COMFYUI_TEST_SAMPLER", "euler"),
            scheduler=os.environ.get("COMFYUI_TEST_SCHEDULER", "normal"),
            denoise=float(os.environ.get("COMFYUI_TEST_DENOISE", "0.65")),
        )

        # Act
        events = []
        result = GenerationCoordinator(client).run(request, on_event=events.append)
        output_bytes = client.view_image(result.images[0])

        # Assert
        assert result.prompt_id
        assert result.images
        assert output_bytes.startswith(b"\x89PNG\r\n\x1a\n")
        assert any(event.event_type in {
            ComfyUIEventType.PROGRESS,
            ComfyUIEventType.EXECUTING,
            ComfyUIEventType.EXECUTED,
        } for event in events)