import threading
from threading import Event

import pytest

from comfyui_plugin.client import ComfyImage, ComfyUICancelledError

from comfyui_plugin.generation import GenerationCoordinator, GenerationRequest, parse_lora_settings


class FakeClient:
    def __init__(self):
        self.queued_workflow = None

    def queue_prompt(self, workflow):
        self.queued_workflow = workflow
        return "job-1"

    def wait_for_outputs(self, prompt_id, **_kwargs):
        return [ComfyImage("result.png", "", "output")]


class TestGenerationCoordinator:
    def test_runs_prepared_workflow_and_reports_result(self):
        # Arrange
        client = FakeClient()
        coordinator = GenerationCoordinator(client)
        request = GenerationRequest(
            workflow={"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
            prompt="portrait",
            negative_prompt="blurry",
            seed=42,
        )

        # Act
        result = coordinator.run(request)

        # Assert
        assert result.prompt_id == "job-1"
        assert result.seed == 42
        assert result.images[0].filename == "result.png"
        assert client.queued_workflow["1"]["inputs"]["seed"] == 42

    def test_passes_mask_image_to_workflow_preparation(self):
        # Arrange
        client = FakeClient()
        request = GenerationRequest(
            workflow={"1": {"class_type": "VAEEncodeForInpaint", "inputs": {"mask": "old-mask"}}},
            prompt="portrait",
            negative_prompt="blurry",
            mask_image="uploads/mask.png",
        )

        # Act
        GenerationCoordinator(client).run(request)

        # Assert
        assert client.queued_workflow["2"]["class_type"] == "LoadImageMask"
        assert client.queued_workflow["1"]["inputs"]["mask"] == ["2", 0]

    def test_cancellation_before_queueing_does_not_submit_prompt(self):
        # Arrange
        client = FakeClient()
        cancellation_event = Event()
        cancellation_event.set()
        request = GenerationRequest(
            workflow={"1": {"class_type": "KSampler", "inputs": {}}},
            prompt="portrait",
            negative_prompt="blurry",
        )

        # Act
        with pytest.raises(RuntimeError, match="before queueing"):
            GenerationCoordinator(client).run(request, cancellation_event=cancellation_event)

        # Assert
        assert client.queued_workflow is None

    def test_cancellation_during_polling_interrupts_and_clears_active_prompt(self):
        # Arrange
        client = BlockingClient()
        coordinator = GenerationCoordinator(client)
        request = GenerationRequest(
            workflow={"1": {"class_type": "KSampler", "inputs": {}}},
            prompt="portrait",
            negative_prompt="blurry",
        )
        thread = threading.Thread(target=_run_and_capture, args=(coordinator, request))

        # Act
        thread.start()
        client.started.wait(timeout=1)
        assert coordinator.active_prompt_ids == ("job-1",)
        coordinator.cancel()
        thread.join(timeout=1)

        # Assert
        assert isinstance(client.error, RuntimeError)
        assert "cancelled" in str(client.error)
        assert client.interrupted
        assert coordinator.active_prompt_ids == ()

    def test_cancellation_after_completion_keeps_result(self):
        # Arrange
        client = FakeClient()
        coordinator = GenerationCoordinator(client)
        request = GenerationRequest(
            workflow={"1": {"class_type": "KSampler", "inputs": {}}},
            prompt="portrait",
            negative_prompt="blurry",
        )

        # Act
        result = coordinator.run(request)
        coordinator.cancel()

        # Assert
        assert result.prompt_id == "job-1"


class BlockingClient(FakeClient):
    def __init__(self):
        super().__init__()
        self.started = threading.Event()
        self.interrupted = False
        self.error = None

    def wait_for_outputs(self, prompt_id, cancellation_event=None):
        self.started.set()
        while not cancellation_event.is_set():
            pass
        raise ComfyUICancelledError(f"ComfyUI prompt {prompt_id} was cancelled")

    def interrupt(self):
        self.interrupted = True
        return {"ok": True}


def _run_and_capture(coordinator, request):
    try:
        coordinator.run(request)
    except RuntimeError as error:
        coordinator.client.error = error

    def test_submits_typed_defaults_for_workflow_inputs(self):
        # Arrange
        client = FakeClient()
        coordinator = GenerationCoordinator(client)
        request = GenerationRequest(
            workflow={
                "1": {
                    "class_type": "KSampler",
                    "inputs": {
                        "seed": "{{seed}}",
                        "steps": "{{steps}}",
                        "cfg": "{{cfg}}",
                        "sampler_name": "{{sampler}}",
                        "scheduler": "{{scheduler}}",
                        "denoise": "{{denoise}}",
                    },
                }
            },
            prompt="portrait",
            negative_prompt="blurry",
        )

        # Act
        coordinator.run(request)

        # Assert
        inputs = client.queued_workflow["1"]["inputs"]
        assert inputs == {
            "seed": inputs["seed"],
            "steps": 20,
            "cfg": 8.0,
            "sampler_name": "euler",
            "scheduler": "normal",
            "denoise": 1.0,
        }
        assert all("{{" not in str(value) for value in inputs.values())


class TestParseLoraSettings:
    def test_parses_named_strengths_and_default_strength(self):
        # Arrange
        value = "style.safetensors:0.75, detail.safetensors"

        # Act
        loras = parse_lora_settings(value)

        # Assert
        assert loras == {"style.safetensors": 0.75, "detail.safetensors": 1.0}

    def test_rejects_non_numeric_strength(self):
        # Arrange
        value = "style.safetensors:strong"

        # Act
        with pytest.raises(ValueError, match="Invalid LoRA strength"):
            parse_lora_settings(value)