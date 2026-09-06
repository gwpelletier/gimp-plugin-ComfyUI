import os
from pathlib import Path

import pytest

from comfyui_plugin.client import ComfyUIClient
from comfyui_plugin.generation import GenerationCoordinator, GenerationRequest
from comfyui_plugin.workflow import load_workflow


pytestmark = pytest.mark.integration

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_WORKFLOW = REPOSITORY_ROOT / "workflows" / "sdxl-inpainting-api.json"
DEFAULT_SOURCE_IMAGE = REPOSITORY_ROOT / "test" / "fixtures" / "priority-1" / "source.png"
DEFAULT_MASK_IMAGE = REPOSITORY_ROOT / "test" / "fixtures" / "priority-1" / "mask.png"


def _required_environment():
    names = ("COMFYUI_URL", "COMFYUI_CHECKPOINT")
    return [name for name in names if not os.environ.get(name)]


@pytest.mark.skipif(
    _required_environment(),
    reason="Set COMFYUI_URL and COMFYUI_CHECKPOINT; committed workflow and PNG fixtures are used by default",
)
class TestComfyUIInpaintingFlow:
    def test_uploads_source_and_mask_and_retrieves_inpainted_image(self):
        # Arrange
        client = ComfyUIClient(os.environ["COMFYUI_URL"], timeout=60)
        workflow_path = Path(os.environ.get("COMFYUI_MASK_WORKFLOW", DEFAULT_WORKFLOW))
        source_path = Path(os.environ.get("COMFYUI_TEST_IMAGE", DEFAULT_SOURCE_IMAGE))
        mask_path = Path(os.environ.get("COMFYUI_TEST_MASK", DEFAULT_MASK_IMAGE))
        source_upload = client.upload_image(source_path, subfolder="gimp-comfyui-test")
        mask_upload = client.upload_image(mask_path, subfolder="gimp-comfyui-test")
        source_name = "/".join(part for part in (source_upload.subfolder, source_upload.filename) if part)
        mask_name = "/".join(part for part in (mask_upload.subfolder, mask_upload.filename) if part)
        request = GenerationRequest(
            workflow=load_workflow(workflow_path),
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