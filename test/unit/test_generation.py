from comfyui_plugin.client import ComfyImage
import pytest

from comfyui_plugin.generation import GenerationCoordinator, GenerationRequest, parse_lora_settings


class FakeClient:
    def __init__(self):
        self.queued_workflow = None

    def queue_prompt(self, workflow):
        self.queued_workflow = workflow
        return "job-1"

    def wait_for_outputs(self, prompt_id):
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
        assert result.images[0].filename == "result.png"
        assert client.queued_workflow["1"]["inputs"]["seed"] == 42

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