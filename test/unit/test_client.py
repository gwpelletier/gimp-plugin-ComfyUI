import json

import pytest

from comfyui_plugin.client import (
    ComfyImage,
    ComfyUICancelledError,
    ComfyUIClient,
    ComfyUIError,
    ComfyUIEventType,
    parse_websocket_event,
)
from comfyui_plugin.workflow import WorkflowError


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

    def test_reads_requested_flux_clip_input(self, monkeypatch):
        # Arrange
        client = ComfyUIClient("http://127.0.0.1:8188")
        requested_inputs = []

        def get_options(node_class, input_name):
            requested_inputs.append((node_class, input_name))
            return [input_name]

        monkeypatch.setattr(client, "get_node_input_options", get_options)

        # Act
        clip_t5 = client.get_available_clip_models("clip_name2")

        # Assert
        assert clip_t5 == ["clip_name2"]
        assert requested_inputs == [("DualCLIPLoader", "clip_name2")]

    def test_reads_local_krea2_clip_options(self, monkeypatch):
        # Arrange
        client = ComfyUIClient("http://127.0.0.1:8188")
        monkeypatch.setattr(client, "get_node_input_options", lambda node_class, input_name: [node_class, input_name])

        # Act
        clips = client.get_available_krea_clips()

        # Assert
        assert clips == ["CLIPLoader", "clip_name"]

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

    def test_parses_progress_event_from_bytes_payload(self):
        # Arrange
        payload = b'{"type": "progress", "data": {"value": 2, "max": 8}}'

        # Act
        event = parse_websocket_event(payload)

        # Assert
        assert event.event_type == ComfyUIEventType.PROGRESS
        assert event.value == 2
        assert event.maximum == 8

    def test_parse_websocket_event_rejects_non_object_message(self):
        # Act / Assert
        with pytest.raises(ComfyUIError, match="must be a JSON object"):
            parse_websocket_event("[1, 2, 3]")

    def test_parse_websocket_event_normalizes_non_dict_data_to_empty(self):
        # Arrange
        payload = {"type": "status", "data": "unexpected"}

        # Act
        event = parse_websocket_event(payload)

        # Assert
        assert event.event_type == ComfyUIEventType.STATUS
        assert event.data == {}
        assert event.prompt_id is None
        assert event.value is None

    def test_open_websocket_targets_client_scoped_ws_endpoint(self):
        # Arrange
        client = ComfyUIClient("http://comfy.example:8188", client_id="abc")

        # Act
        transport = client.open_websocket()

        # Assert
        assert transport.url.startswith("ws://comfy.example:8188/ws?")
        assert "clientId=abc" in transport.url
        assert transport.timeout == client.timeout

    def test_open_websocket_uses_secure_scheme_and_timeout_override(self):
        # Arrange
        client = ComfyUIClient("https://comfy.example", client_id="abc")

        # Act
        transport = client.open_websocket(timeout=5.0)

        # Assert
        assert transport.url.startswith("wss://comfy.example/ws?")
        assert transport.timeout == 5.0

    def test_clear_queue_posts_clear_request_to_queue_endpoint(self, monkeypatch):
        # Arrange
        client = ComfyUIClient("http://127.0.0.1:8188")
        calls = []

        def record(method, path, body=None, content_type=None):
            calls.append((method, path, body, content_type))
            return {}

        monkeypatch.setattr(client, "_json_request", record)

        # Act
        client.clear_queue()

        # Assert
        assert calls == [("POST", "/queue", json.dumps({"clear": True}).encode(), "application/json")]

    def test_reads_available_loras_vaes_and_unets(self, comfyui_server):
        # Arrange
        client = ComfyUIClient(comfyui_server.url)

        # Act
        loras = client.get_available_loras()
        vaes = client.get_available_vaes()
        unets = client.get_available_unets()

        # Assert
        assert loras == ["models/lora.safetensors"]
        assert vaes == ["models/vae.safetensors"]
        assert unets == ["models/unet.safetensors"]

    def test_reads_available_schedulers(self, comfyui_server):
        # Arrange
        client = ComfyUIClient(comfyui_server.url)

        # Act
        schedulers = client.get_available_schedulers()

        # Assert
        assert schedulers == ["normal"]

    def test_available_krea_models_is_empty_when_node_is_absent(self, monkeypatch):
        # Arrange
        client = ComfyUIClient("http://127.0.0.1:8188")
        monkeypatch.setattr(client, "get_object_info", lambda: {"CheckpointLoaderSimple": {}})

        # Act
        models = client.get_available_krea_models()

        # Assert
        assert models == []

    def test_validate_workflow_accepts_schema_compatible_workflow(self, comfyui_server):
        # Arrange
        client = ComfyUIClient(comfyui_server.url)
        workflow = {"1": {"class_type": "KSampler", "inputs": {"sampler_name": "euler", "scheduler": "normal"}}}

        # Act
        result = client.validate_workflow(workflow)

        # Assert
        assert result is None

    def test_validate_workflow_rejects_unavailable_node(self, comfyui_server):
        # Arrange
        client = ComfyUIClient(comfyui_server.url)
        workflow = {"1": {"class_type": "GhostNode", "inputs": {}}}

        # Act / Assert
        with pytest.raises(WorkflowError, match="unavailable node GhostNode"):
            client.validate_workflow(workflow)

    def test_wait_for_outputs_cancels_before_first_poll(self, comfyui_server):
        # Arrange
        client = ComfyUIClient(comfyui_server.url)

        class _AlreadySet:
            def is_set(self):
                return True

        # Act / Assert
        with pytest.raises(ComfyUICancelledError, match="job-1 was cancelled"):
            client.wait_for_outputs("job-1", poll_interval=0, cancellation_event=_AlreadySet())

    def test_wait_for_outputs_times_out_when_prompt_never_finishes(self, monkeypatch):
        # Arrange
        client = ComfyUIClient("http://127.0.0.1:8188")
        monkeypatch.setattr(client, "_request", lambda *args: b"{}")
        clock = iter([0.0, 0.0, 100.0])
        monkeypatch.setattr("comfyui_plugin.client.time.monotonic", lambda: next(clock))
        monkeypatch.setattr("comfyui_plugin.client.time.sleep", lambda _seconds: None)

        # Act / Assert
        with pytest.raises(ComfyUIError, match="Timed out waiting for ComfyUI workflow job-1"):
            client.wait_for_outputs("job-1", poll_interval=0, timeout=1.0)

    def test_wait_for_outputs_reports_cancellation_after_loop_exit(self, monkeypatch):
        # Arrange
        client = ComfyUIClient("http://127.0.0.1:8188")
        monkeypatch.setattr(client, "_request", lambda *args: b"{}")
        clock = iter([0.0, 0.0, 100.0])
        monkeypatch.setattr("comfyui_plugin.client.time.monotonic", lambda: next(clock))
        monkeypatch.setattr("comfyui_plugin.client.time.sleep", lambda _seconds: None)

        class _SetsAfterLoop:
            def __init__(self):
                self.checks = 0

            def is_set(self):
                self.checks += 1
                return self.checks > 1

        # Act / Assert
        with pytest.raises(ComfyUICancelledError, match="job-1 was cancelled"):
            client.wait_for_outputs("job-1", poll_interval=0, timeout=1.0, cancellation_event=_SetsAfterLoop())

    def test_view_image_downloads_bytes_for_image_query(self, monkeypatch):
        # Arrange
        client = ComfyUIClient("http://127.0.0.1:8188")
        requested = {}

        def record(method, path):
            requested["method"] = method
            requested["path"] = path
            return b"PNGDATA"

        monkeypatch.setattr(client, "_request", record)
        image = ComfyImage("result.png", "batch", "output")

        # Act
        data = client.view_image(image)

        # Assert
        assert data == b"PNGDATA"
        assert requested["method"] == "GET"
        assert requested["path"] == "/view?filename=result.png&subfolder=batch&type=output"

    def test_json_request_rejects_invalid_json_body(self, monkeypatch):
        # Arrange
        client = ComfyUIClient("http://127.0.0.1:8188")
        monkeypatch.setattr(client, "_request", lambda *args: b"not-json")

        # Act / Assert
        with pytest.raises(ComfyUIError, match="invalid JSON for GET /system_stats"):
            client.get_system_stats()