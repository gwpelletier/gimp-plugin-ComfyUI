import os
import threading
import time

import pytest

from comfyui_plugin.client import ComfyUIClient
from comfyui_plugin.generation import GenerationCancelledError, GenerationCoordinator, GenerationRequest
from comfyui_plugin.workflow import load_workflow


pytestmark = pytest.mark.integration


def _required_environment():
    names = ("COMFYUI_URL", "COMFYUI_CANCEL_WORKFLOW", "COMFYUI_CHECKPOINT")
    return [name for name in names if not os.environ.get(name)]


@pytest.mark.skipif(
    _required_environment(),
    reason="Set COMFYUI_URL, COMFYUI_CANCEL_WORKFLOW, and COMFYUI_CHECKPOINT for a long-running cancellation flow",
)
class TestComfyUICancellationFlow:
    def test_long_running_prompt_cancels_without_returning_outputs(self):
        # Arrange
        client = ComfyUIClient(os.environ["COMFYUI_URL"], timeout=60)
        coordinator = GenerationCoordinator(client)
        request = GenerationRequest(
            workflow=load_workflow(os.environ["COMFYUI_CANCEL_WORKFLOW"]),
            prompt=os.environ.get("COMFYUI_CANCEL_PROMPT", "cancellation test"),
            negative_prompt=os.environ.get("COMFYUI_CANCEL_NEGATIVE_PROMPT", "low quality"),
            checkpoint=os.environ["COMFYUI_CHECKPOINT"],
            steps=int(os.environ.get("COMFYUI_CANCEL_STEPS", "1000")),
        )
        outcome = {}

        def run_generation():
            try:
                coordinator.run(request)
            except Exception as error:
                outcome["error"] = error

        worker = threading.Thread(target=run_generation)

        # Act
        worker.start()
        deadline = time.monotonic() + 10
        while not coordinator.active_prompt_ids and time.monotonic() < deadline:
            time.sleep(0.1)
        coordinator.cancel()
        worker.join(timeout=60)

        # Assert
        assert not worker.is_alive()
        assert isinstance(outcome.get("error"), GenerationCancelledError)
        assert coordinator.active_prompt_ids == ()