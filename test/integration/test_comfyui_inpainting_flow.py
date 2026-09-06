import os
from pathlib import Path

import pytest

from comfyui_plugin.client import ComfyUIClient
from comfyui_plugin.generation import GenerationCoordinator, GenerationRequest
from comfyui_plugin.workflow import load_workflow


pytestmark = pytest.mark.integration


def _required_environment():
    names = (
        "COMFYUI_URL",
        "COMFYUI_MASK_WORKFLOW",
        "COMFYUI_TEST_IMAGE",
        "COMFYUI_TEST_MASK",
        "COMFYUI_CHECKPOINT",
    )
    return [name for name in names if not os.environ.get(name)]


@pytest.mark.skipif(
    _required_environment(),
    reason="Set COMFYUI_URL, COMFYUI_MASK_WORKFLOW, COMFYUI_TEST_IMAGE, COMFYUI_TEST_MASK, and COMFYUI_CHECKPOINT",
)
class TestComfyUIInpaintingFlow:
    def test_uploads_source_and_mask_and_retrieves_inpainted_image(self):
        # Arrange
        client = ComfyUIClient(os.environ["COMFYUI_URL"], timeout=60)
        source_upload = client.upload_image(Path(os.environ["COMFYUI_TEST_IMAGE"]), subfolder="gimp-comfyui-test")
        mask_upload = client.upload_image(Path(os.environ["COMFYUI_TEST_MASK"]), subfolder="gimp-comfyui-test")
        source_name = "/".join(part for part in (source_upload.subfolder, source_upload.filename) if part)
        mask_name = "/".join(part for part in (mask_upload.subfolder, mask_upload.filename) if part)
        request = GenerationRequest(
            workflow=load_workflow(os.environ["COMFYUI_MASK_WORKFLOW"]),
            prompt=os.environ.get("COMFYUI_TEST_PROMPT", "a clean restored portrait"),
            negative_prompt=os.environ.get("COMFYUI_TEST_NEGATIVE_PROMPT", "blurry, distorted, low quality"),
            checkpoint=os.environ["COMFYUI_CHECKPOINT"],
            input_image=source_name,
            mask_image=mask_name,
            seed=int(os.environ.get("COMFYUI_TEST_SEED", "20260905")),
            steps=int(os.environ.get("COMFYUI_TEST_STEPS", "6")),
            cfg=float(os.environ.get("COMFYUI_TEST_CFG", "7")),
            sampler=os.environ.get("COMFYUI_TEST_SAMPLER", "euler"),
            scheduler=os.environ.get("COMFYUI_TEST_SCHEDULER", "normal"),
            denoise=float(os.environ.get("COMFYUI_TEST_DENOISE", "0.65")),
        )

        # Act
        result = GenerationCoordinator(client).run(request)
        output_bytes = client.view_image(result.images[0])

        # Assert
        assert result.prompt_id
        assert result.images
        assert output_bytes.startswith(b"\x89PNG\r\n\x1a\n")