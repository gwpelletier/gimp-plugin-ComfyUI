from comfyui_plugin.websocket import ComfyUIPreview, ComfyUIWebSocket


class TestComfyUIWebSocket:
    def test_adds_client_id_to_websocket_url(self):
        # Arrange
        websocket = ComfyUIWebSocket("ws://127.0.0.1:8188/ws", client_id="client-1")

        # Act
        url = websocket.url

        # Assert
        assert url == "ws://127.0.0.1:8188/ws?clientId=client-1"

    def test_decodes_binary_preview_frame(self, monkeypatch):
        # Arrange
        websocket = ComfyUIWebSocket("ws://127.0.0.1:8188/ws", client_id="client-1")
        websocket._socket = object()
        monkeypatch.setattr(websocket, "_read_frame", lambda: (2, b"\x00\x00\x00\x01\x00\x00\x00\x02preview"))

        # Act
        preview = websocket.receive()

        # Assert
        assert isinstance(preview, ComfyUIPreview)
        assert preview.image_format == 2
        assert preview.data == b"preview"