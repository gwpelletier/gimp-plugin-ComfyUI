import pytest

from test.support.comfyui_server import FakeComfyUIServer


@pytest.fixture
def comfyui_server():
    """Provide an isolated local HTTP boundary for ComfyUI client tests."""
    server = FakeComfyUIServer()
    server.start()
    try:
        yield server
    finally:
        server.stop()