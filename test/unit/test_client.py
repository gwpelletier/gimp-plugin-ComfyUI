from comfyui_plugin.client import ComfyUIClient


class TestComfyUIClient:
    def test_health_check_uses_comfyui_boundary(self, comfyui_server):
        # Arrange
        client = ComfyUIClient(comfyui_server.url)

        # Act
        is_healthy = client.health_check()

        # Assert
        assert is_healthy

    def test_queue_and_wait_for_outputs_returns_generated_images(self, comfyui_server):
        # Arrange
        client = ComfyUIClient(comfyui_server.url)

        # Act
        prompt_id = client.queue_prompt({"1": {"class_type": "LoadImage"}})
        outputs = client.wait_for_outputs(prompt_id, poll_interval=0)

        # Assert
        assert prompt_id == "job-1"
        assert outputs[0].filename == "result.png"