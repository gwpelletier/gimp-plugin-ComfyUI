import json

import pytest

from comfyui_plugin.client import (
    ComfyUIClient,
    ComfyUIError,
    ComfyUIEventType,
    parse_websocket_event,
)


class TestComfyUIClient:
    def test_parses_progress_websocket_event(self):
        # Arrange
        payload = '{"type": "progress", "data": {"prompt_id": "job-1", "value": 3, "max": 10}}'

        # Act
        event = parse_websocket_event(payload)

        # Assert
        assert event.event_type == ComfyUIEventType.PROGRESS
        assert event.prompt_id == "job-1"
        assert event.value == 3
        assert event.maximum == 10

    def test_parses_execution_error_and_unknown_events(self):
        # Arrange
        error_event = parse_websocket_event({"type": "execution_error", "data": {"node": 4}})
        unknown_event = parse_websocket_event({"type": "future_event", "data": {}})

        # Act
        error_type = error_event.event_type
        unknown_type = unknown_event.event_type

        # Assert
        assert error_type == ComfyUIEventType.EXECUTION_ERROR
        assert error_event.node_id == "4"
        assert unknown_type == ComfyUIEventType.UNKNOWN

    def test_health_check_returns_false_when_server_is_unreachable(self):
        # Arrange
        client = ComfyUIClient("http://127.0.0.1:1", timeout=0.1)

        # Act
        is_healthy = client.health_check()

        # Assert
        assert not is_healthy

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

    def test_interrupt_returns_comfyui_response(self, comfyui_server):
        # Arrange
        client = ComfyUIClient(comfyui_server.url)

        # Act
        response = client.interrupt()

        # Assert
        assert response == {"prompt_id": "job-1"}

    def test_wait_for_outputs_returns_all_image_references(self, comfyui_server, monkeypatch):
        # Arrange
        client = ComfyUIClient(comfyui_server.url)
        response = {
            "job-1": {
                "outputs": {
                    "node": {
                        "images": [
                            {"filename": "first.png"},
                            {"filename": "second.png", "subfolder": "batch", "type": "output"},
                        ]
                    }
                }
            }
        }
        monkeypatch.setattr(client, "_request", lambda *args: json.dumps(response).encode())

        # Act
        outputs = client.wait_for_outputs("job-1", poll_interval=0)

        # Assert
        assert [image.filename for image in outputs] == ["first.png", "second.png"]
        assert outputs[1].subfolder == "batch"

    def test_node_metadata_is_cached_and_exposes_input_options(self, comfyui_server):
        # Arrange
        client = ComfyUIClient(comfyui_server.url)

        # Act
        checkpoints = client.get_available_checkpoints()
        samplers = client.get_available_samplers()

        # Assert
        assert checkpoints == ["models/checkpoint.safetensors"]
        assert samplers == ["euler"]

    def test_node_metadata_returns_empty_options_for_unknown_input(self, comfyui_server):
        # Arrange
        client = ComfyUIClient(comfyui_server.url)

        # Act
        options = client.get_node_input_options("MissingNode", "missing_input")

        # Assert
        assert options == []

    def test_reads_dynamic_krea_model_options(self, monkeypatch):
        # Arrange
        client = ComfyUIClient("http://127.0.0.1:8188")
        monkeypatch.setattr(
            client,
            "get_object_info",
            lambda: {"Krea2ImageNode": {"input": {"required": {"model": ["DYNAMIC", {"options": [{"key": "Krea 2 Medium"}, {"key": "Krea 2 Large"}]}]}}}},
        )

        # Act
        models = client.get_available_krea_models()

        # Assert
        assert models == ["Krea 2 Medium", "Krea 2 Large"]

    def test_upload_image_returns_server_reference(self, comfyui_server, tmp_path):
        # Arrange
        image_path = tmp_path / "source.png"
        image_path.write_bytes(b"not-a-real-png")
        client = ComfyUIClient(comfyui_server.url)

        # Act
        uploaded = client.upload_image(image_path)

        # Assert
        assert uploaded.filename == "uploaded.png"
        assert uploaded.folder_type == "input"

    def test_upload_image_rejects_missing_file(self, comfyui_server, tmp_path):
        # Arrange
        client = ComfyUIClient(comfyui_server.url)

        # Act
        with pytest.raises(ComfyUIError, match="does not exist"):
            client.upload_image(tmp_path / "missing.png")

        # Assert
        assert not (tmp_path / "missing.png").exists()

    def test_queue_prompt_rejects_server_error(self, comfyui_server, monkeypatch):
        # Arrange
        client = ComfyUIClient(comfyui_server.url)
        monkeypatch.setattr(client, "_request", lambda *args: json.dumps({"error": "invalid graph"}).encode())

        # Act
        with pytest.raises(ComfyUIError, match="rejected workflow"):
            client.queue_prompt({})

    def test_system_stats_rejects_non_object_json(self, comfyui_server, monkeypatch):
        # Arrange
        client = ComfyUIClient(comfyui_server.url)
        monkeypatch.setattr(client, "_request", lambda *args: b"[]")

        # Act
        with pytest.raises(ComfyUIError, match="non-object"):
            client.get_system_stats()

    def test_wait_for_outputs_raises_for_execution_error(self, comfyui_server, monkeypatch):
        # Arrange
        client = ComfyUIClient(comfyui_server.url)
        response = {"job-1": {"status": {"status_str": "error"}}}
        monkeypatch.setattr(client, "_request", lambda *args: json.dumps(response).encode())

        # Act
        with pytest.raises(ComfyUIError, match="failed workflow"):
            client.wait_for_outputs("job-1", poll_interval=0)