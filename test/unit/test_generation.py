import threading
from threading import Event

import pytest

from comfyui_plugin.client import ComfyImage, ComfyUICancelledError, ComfyUIEvent, ComfyUIEventType

from comfyui_plugin.generation import (
    GenerationCancelledError,
    GenerationCoordinator,
    GenerationRequest,
    parse_lora_settings,
)


class FakeClient:
    def __init__(self):
        self.queued_workflow = None

    def queue_prompt(self, workflow):
        self.queued_workflow = workflow
        return "job-1"

    def wait_for_outputs(self, prompt_id, **_kwargs):
        return [ComfyImage("result.png", "", "output")]


class TestGenerationCoordinator:
    def test_reports_websocket_progress_events_without_replacing_rest_completion(self):
        # Arrange
        client = EventClient()
        events = []
        request = GenerationRequest(
            workflow={"1": {"class_type": "KSampler", "inputs": {}}},
            prompt="portrait",
            negative_prompt="blurry",
        )

        # Act
        result = GenerationCoordinator(client).run(request, on_event=events.append)

        # Assert
        assert result.prompt_id == "job-1"
        assert [event.event_type for event in events] == [
            ComfyUIEventType.PROGRESS,
            ComfyUIEventType.EXECUTED,
        ]
        assert events[1].node_id == "1"
        assert events[1].node_type == "KSampler"

    def test_rest_completion_survives_websocket_setup_failure(self):
        # Arrange
        client = BrokenWebSocketClient()
        request = GenerationRequest(
            workflow={"1": {"class_type": "KSampler", "inputs": {}}},
            prompt="portrait",
            negative_prompt="blurry",
        )

        # Act
        result = GenerationCoordinator(client).run(request)

        # Assert
        assert result.prompt_id == "job-1"

    def test_runs_batch_sequentially_and_isolates_workflow_state(self):
        # Arrange
        client = FakeClient()
        coordinator = GenerationCoordinator(client)
        requests = [
            GenerationRequest(
                workflow={"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt="first",
                negative_prompt="",
                seed=1,
            ),
            GenerationRequest(
                workflow={"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt="second",
                negative_prompt="",
                seed=2,
            ),
        ]

        # Act
        summary = coordinator.run_batch(requests)

        # Assert
        assert [item.result.seed for item in summary.completed] == [1, 2]
        assert requests[0].workflow["1"]["inputs"]["seed"] == 1

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

    def test_reports_final_progress_after_completion(self):
        # Arrange
        client = FakeClient()
        progress = []
        request = GenerationRequest(
            workflow={"1": {"class_type": "KSampler", "inputs": {}}},
            prompt="portrait",
            negative_prompt="blurry",
        )

        # Act
        result = GenerationCoordinator(client).run(
            request, on_progress=lambda value, maximum: progress.append((value, maximum))
        )

        # Assert
        assert result.prompt_id == "job-1"
        assert progress == [(1, 1)]

    def test_cancellation_after_polling_raises_and_clears_active_prompt(self):
        # Arrange
        cancellation_event = Event()
        client = CancellingAfterPollClient(cancellation_event)
        coordinator = GenerationCoordinator(client)
        request = GenerationRequest(
            workflow={"1": {"class_type": "KSampler", "inputs": {}}},
            prompt="portrait",
            negative_prompt="blurry",
        )

        # Act
        with pytest.raises(GenerationCancelledError, match="job-1 was cancelled"):
            coordinator.run(request, cancellation_event=cancellation_event)

        # Assert
        assert client.queued_workflow["1"]["class_type"] == "KSampler"
        assert coordinator.active_prompt_ids == ()

    def test_discards_malformed_and_foreign_prompt_events(self):
        # Arrange
        client = ScriptedEventClient((
            None,
            "not-a-comfyui-event",
            ComfyUIEvent(ComfyUIEventType.PROGRESS, "other-job", value=1, maximum=4),
            ComfyUIEvent(ComfyUIEventType.EXECUTED, "job-1", node_id="1"),
        ))
        events = []
        request = GenerationRequest(
            workflow={"1": {"class_type": "KSampler", "inputs": {}}},
            prompt="portrait",
            negative_prompt="blurry",
        )

        # Act
        result = GenerationCoordinator(client).run(request, on_event=events.append)

        # Assert
        assert result.prompt_id == "job-1"
        assert [(event.event_type, event.prompt_id) for event in events] == [
            (ComfyUIEventType.EXECUTED, "job-1")
        ]

    def test_delivers_event_unchanged_when_node_is_unknown(self):
        # Arrange
        client = ScriptedEventClient((
            ComfyUIEvent(ComfyUIEventType.EXECUTING, "job-1", node_id="99"),
            ComfyUIEvent(ComfyUIEventType.EXECUTED, "job-1"),
        ))
        events = []
        request = GenerationRequest(
            workflow={"1": {"class_type": "KSampler", "inputs": {}}},
            prompt="portrait",
            negative_prompt="blurry",
        )

        # Act
        GenerationCoordinator(client).run(request, on_event=events.append)

        # Assert
        assert [(event.node_id, event.node_type) for event in events] == [("99", None), (None, None)]

    def test_reports_websocket_progress_when_on_event_is_omitted(self):
        # Arrange
        client = ScriptedEventClient((
            ComfyUIEvent(ComfyUIEventType.PROGRESS, "job-1", value=2, maximum=10),
            ComfyUIEvent(ComfyUIEventType.EXECUTED, "job-1"),
        ))
        progress = []
        request = GenerationRequest(
            workflow={"1": {"class_type": "KSampler", "inputs": {}}},
            prompt="portrait",
            negative_prompt="blurry",
        )

        # Act
        GenerationCoordinator(client).run(
            request, on_progress=lambda value, maximum: progress.append((value, maximum))
        )

        # Assert
        assert progress == [(2, 10), (1, 1)]

    def test_closes_websocket_when_rest_completion_finishes_first(self):
        # Arrange
        client = IdleWebSocketClient()
        request = GenerationRequest(
            workflow={"1": {"class_type": "KSampler", "inputs": {}}},
            prompt="portrait",
            negative_prompt="blurry",
        )

        # Act
        result = GenerationCoordinator(client).run(request)

        # Assert
        assert result.prompt_id == "job-1"
        assert client.websocket.closed


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


class EventClient(FakeClient):
    def __init__(self):
        super().__init__()
        self.event_seen = threading.Event()

    def open_websocket(self, **_kwargs):
        return EventWebSocket(self.event_seen)

    def wait_for_outputs(self, prompt_id, **_kwargs):
        assert self.event_seen.wait(timeout=1)
        return super().wait_for_outputs(prompt_id)


class EventWebSocket:
    def __init__(self, event_seen):
        self.event_seen = event_seen
        self.events = iter((
            ComfyUIEvent(ComfyUIEventType.PROGRESS, "job-1", value=2, maximum=10),
            ComfyUIEvent(ComfyUIEventType.EXECUTED, "job-1", node_id="1"),
        ))

    def connect(self):
        pass

    def receive(self):
        event = next(self.events)
        if event.event_type == ComfyUIEventType.EXECUTED:
            self.event_seen.set()
        return event

    def close(self):
        pass


class BrokenWebSocketClient(FakeClient):
    def open_websocket(self, **_kwargs):
        raise OSError("WebSocket unavailable")


class CancellingAfterPollClient(FakeClient):
    """Cancel through the caller's event after polling completes normally."""

    def __init__(self, cancellation_event):
        super().__init__()
        self.cancellation_event = cancellation_event

    def wait_for_outputs(self, prompt_id, **kwargs):
        self.cancellation_event.set()
        return super().wait_for_outputs(prompt_id)


class ScriptedWebSocket:
    def __init__(self, events, event_seen):
        self.events = iter(events)
        self.event_seen = event_seen
        self.closed = False

    def connect(self):
        pass

    def receive(self):
        event = next(self.events)
        if isinstance(event, ComfyUIEvent) and event.event_type == ComfyUIEventType.EXECUTED:
            self.event_seen.set()
        return event

    def close(self):
        self.closed = True


class ScriptedEventClient(FakeClient):
    def __init__(self, events):
        super().__init__()
        self.event_seen = threading.Event()
        self.websocket = ScriptedWebSocket(events, self.event_seen)

    def open_websocket(self, **_kwargs):
        return self.websocket

    def wait_for_outputs(self, prompt_id, **kwargs):
        assert self.event_seen.wait(timeout=1)
        return super().wait_for_outputs(prompt_id)


class IdleWebSocket:
    """Block in receive() until REST polling completes so the observer outlives the run."""

    def __init__(self, rest_completed):
        self.rest_completed = rest_completed
        self.closed = False

    def connect(self):
        pass

    def receive(self):
        self.rest_completed.wait(timeout=1)
        return None

    def close(self):
        self.closed = True


class IdleWebSocketClient(FakeClient):
    def __init__(self):
        super().__init__()
        self.rest_completed = threading.Event()
        self.websocket = IdleWebSocket(self.rest_completed)

    def open_websocket(self, **_kwargs):
        return self.websocket

    def wait_for_outputs(self, prompt_id, **kwargs):
        try:
            return super().wait_for_outputs(prompt_id)
        finally:
            self.rest_completed.set()


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

    def test_skips_blank_entries_and_returns_remaining_loras(self):
        # Arrange
        value = "style.safetensors:0.75,, ,detail.safetensors"

        # Act
        loras = parse_lora_settings(value)

        # Assert
        assert loras == {"style.safetensors": 0.75, "detail.safetensors": 1.0}

    def test_rejects_lora_entry_with_empty_name(self):
        # Arrange
        value = ":0.5"

        # Act / Assert
        with pytest.raises(ValueError, match="LoRA name must not be empty"):
            parse_lora_settings(value)