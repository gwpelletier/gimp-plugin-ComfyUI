import json
import struct

import pytest

from comfyui_plugin.client import ComfyUIError, ComfyUIEvent
from comfyui_plugin.websocket import ComfyUIPreview, ComfyUIWebSocket

from test.support.websocket_server import (
    FakeWebSocketServer,
    read_client_frame,
    send_server_frame,
)


@pytest.fixture
def websocket_server():
    """Provide an isolated local WebSocket boundary for transport tests."""
    server = FakeWebSocketServer()
    try:
        yield server
    finally:
        server.stop()


def _connected(websocket_server, exchange):
    """Start the scripted exchange and return a connected, handshake-confirmed client."""
    websocket_server.start(exchange)
    client = ComfyUIWebSocket(websocket_server.url, client_id="client-1", timeout=5)
    client.connect()
    websocket_server.accept_upgrade()
    return client


class TestConnect:
    def test_connect_completes_upgrade_and_requests_client_id(self, websocket_server):
        # Arrange
        websocket_server.start(lambda connection: None)
        client = ComfyUIWebSocket(websocket_server.url, client_id="client-1")

        # Act
        client.connect()

        # Assert
        assert websocket_server.request_line.startswith("GET /ws?clientId=client-1 ")
        assert websocket_server.request_headers.get("upgrade") == "websocket"

    def test_connect_rejects_non_101_response(self):
        # Arrange: a plain TCP peer that answers with an HTTP error instead of upgrading.
        import socket
        from threading import Thread

        listener = socket.create_server(("127.0.0.1", 0))

        def respond():
            connection, _ = listener.accept()
            connection.recv(4096)
            connection.sendall(b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n")
            connection.close()
            listener.close()

        thread = Thread(target=respond, daemon=True)
        thread.start()
        client = ComfyUIWebSocket(f"ws://127.0.0.1:{listener.getsockname()[1]}/ws", client_id="c", timeout=5)

        # Act / Assert
        with pytest.raises(ComfyUIError, match="upgrade was rejected"):
            client.connect()
        thread.join(timeout=5)


class TestReceive:
    def test_receive_returns_parsed_event_for_text_frame(self, websocket_server):
        # Arrange
        event = {"type": "status", "data": {"status": {"exec_info": {"queue_remaining": 0}}}}
        client = _connected(websocket_server, lambda connection: send_server_frame(connection, 0x1, json.dumps(event).encode()))

        # Act
        received = client.receive()

        # Assert
        assert isinstance(received, ComfyUIEvent)
        assert received.event_type == "status"

    def test_receive_returns_preview_for_binary_frame(self, websocket_server):
        # Arrange: 4-byte header + big-endian format word + image bytes.
        payload = b"\x00\x00\x00\x00" + struct.pack(">I", 1) + b"jpeg-bytes"
        client = _connected(websocket_server, lambda connection: send_server_frame(connection, 0x2, payload))

        # Act
        received = client.receive()

        # Assert
        assert isinstance(received, ComfyUIPreview)
        assert received.image_format == 1
        assert received.data == b"jpeg-bytes"

    def test_receive_ignores_truncated_binary_preview(self, websocket_server):
        # Arrange: fewer than the 8 header bytes a preview requires.
        client = _connected(websocket_server, lambda connection: send_server_frame(connection, 0x2, b"\x00\x01\x02"))

        # Act
        received = client.receive()

        # Assert
        assert received is None

    def test_receive_answers_ping_with_pong(self, websocket_server):
        # Arrange
        exchanges = []

        def exchange(connection):
            send_server_frame(connection, 0x9, b"ping-data")
            exchanges.append(read_client_frame(connection))

        client = _connected(websocket_server, exchange)

        # Act
        received = client.receive()
        websocket_server._thread.join(timeout=5)

        # Assert: the client replied with a pong echoing the ping payload.
        assert received is None
        assert exchanges == [(0xA, b"ping-data")]

    def test_receive_closes_on_close_frame(self, websocket_server):
        # Arrange
        client = _connected(websocket_server, lambda connection: send_server_frame(connection, 0x8, b""))

        # Act
        received = client.receive()

        # Assert
        assert received is None
        with pytest.raises(ComfyUIError, match="not connected"):
            client.receive()

    def test_receive_ignores_unknown_opcode(self, websocket_server):
        # Arrange
        client = _connected(websocket_server, lambda connection: send_server_frame(connection, 0x3, b"reserved"))

        # Act
        received = client.receive()

        # Assert
        assert received is None

    def test_receive_handles_fragmented_frame_across_recv_calls(self, websocket_server):
        # Arrange: deliver the frame byte-by-byte so the client must buffer partial recv() results.
        payload = json.dumps({"type": "progress", "data": {"value": 1, "max": 2}}).encode()
        frame = bytes((0x81, len(payload))) + payload

        def exchange(connection):
            for index in range(0, len(frame), 3):
                connection.sendall(frame[index : index + 3])

        client = _connected(websocket_server, exchange)

        # Act
        received = client.receive()

        # Assert
        assert isinstance(received, ComfyUIEvent)
        assert received.event_type == "progress"

    def test_receive_raises_when_server_closes_mid_frame(self, websocket_server):
        # Arrange: declare a 10-byte payload, send 5 bytes, then close the socket.
        def exchange(connection):
            connection.sendall(b"\x81\x0aabcde")
            websocket_server.stop()

        client = _connected(websocket_server, exchange)

        # Act / Assert
        with pytest.raises(ComfyUIError, match="closed unexpectedly"):
            client.receive()

    def test_receive_handles_extended_16bit_length(self, websocket_server):
        # Arrange: pad a valid JSON event past 125 bytes so the 126 extended-length form is used.
        message = {"type": "progress", "data": {"value": 1, "max": 2, "padding": "x" * 300}}
        payload = json.dumps(message).encode()
        assert len(payload) > 125
        client = _connected(websocket_server, lambda connection: send_server_frame(connection, 0x1, payload))

        # Act
        received = client.receive()

        # Assert
        assert isinstance(received, ComfyUIEvent)
        assert received.event_type == "progress"
        assert received.data["padding"] == "x" * 300


class TestClose:
    def test_close_sends_close_frame_to_server(self, websocket_server):
        # Arrange
        exchanges = []

        def exchange(connection):
            exchanges.append(read_client_frame(connection))

        client = _connected(websocket_server, exchange)

        # Act
        client.close()
        websocket_server._thread.join(timeout=5)

        # Assert
        assert exchanges == [(0x8, b"")]

    def test_close_without_connection_is_a_no_op(self):
        # Arrange
        client = ComfyUIWebSocket("ws://127.0.0.1:1/ws", client_id="c")

        # Act / Assert: closing an unopened client must not raise.
        client.close()


class TestUrlValidation:
    def test_rejects_non_websocket_scheme(self):
        # Act / Assert
        with pytest.raises(ValueError, match="ws:// or wss://"):
            ComfyUIWebSocket("http://127.0.0.1:8188/ws", client_id="c")

    def test_with_client_id_merges_existing_query(self):
        # Arrange / Act
        client = ComfyUIWebSocket("ws://h:8188/ws?foo=bar", client_id="c1")

        # Assert
        assert "foo=bar" in client.url
        assert "clientId=c1" in client.url


class TestFrameCodec:
    """Drive the frame codec through a connected pair for masked and long frames."""

    def _pair(self, websocket_server):
        client = _connected(websocket_server, lambda connection: None)
        return websocket_server, client

    def test_receive_handles_masked_server_frame(self, websocket_server):
        # Arrange: a non-conformant but tolerated masked server frame.
        import os

        mask = b"\x01\x02\x03\x04"
        payload = os.urandom(0) or b"{}"
        masked = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))

        def exchange(connection):
            connection.sendall(bytes((0x81, 0x80 | len(payload))) + mask + masked)

        client = _connected(websocket_server, exchange)

        # Act
        received = client.receive()

        # Assert
        assert isinstance(received, ComfyUIEvent)

    def test_receive_handles_extended_64bit_length(self, websocket_server):
        # Arrange: 70000-byte payload requires the 127 (64-bit) extended-length form.
        message = {"type": "progress", "data": {"value": 1, "max": 2, "padding": "y" * 70000}}
        payload = json.dumps(message).encode()
        assert len(payload) > 0xFFFF
        client = _connected(websocket_server, lambda connection: send_server_frame(connection, 0x1, payload))

        # Act
        received = client.receive()

        # Assert
        assert isinstance(received, ComfyUIEvent)
        assert received.event_type == "progress"

    def test_send_frame_uses_extended_headers_for_large_payloads(self, websocket_server):
        # Arrange: capture what the client sends for 126- and 127-length pongs.
        captured = []

        def exchange(connection):
            # Two pings, one 200-byte and one 70000-byte, forcing both extended headers on the pong.
            send_server_frame(connection, 0x9, b"p" * 200)
            captured.append(read_client_frame(connection))
            send_server_frame(connection, 0x9, b"q" * 70000)
            captured.append(read_client_frame(connection))

        client = _connected(websocket_server, exchange)

        # Act
        client.receive()
        client.receive()
        websocket_server._thread.join(timeout=10)

        # Assert: payloads round-trip intact regardless of which header form is used.
        assert captured[0] == (0xA, b"p" * 200)
        assert captured[1] == (0xA, b"q" * 70000)

    def test_close_swallows_oserror_when_socket_already_dead(self, websocket_server):
        # Arrange: substitute a socket whose send fails, as when the peer reset the connection.
        client = _connected(websocket_server, lambda connection: None)

        class DeadSocket:
            def sendall(self, _data):
                raise OSError("connection reset")

            def close(self):
                pass

        client._socket = DeadSocket()

        # Act / Assert: close must not propagate the send error, and must drop the socket.
        client.close()
        assert client._socket is None


class TestDisconnectedGuards:
    def test_receive_raises_when_not_connected(self):
        # Arrange
        client = ComfyUIWebSocket("ws://127.0.0.1:1/ws", client_id="c")

        # Act / Assert
        with pytest.raises(ComfyUIError, match="not connected"):
            client.receive()

    def test_send_frame_without_connection_is_a_no_op(self):
        # Arrange
        client = ComfyUIWebSocket("ws://127.0.0.1:1/ws", client_id="c")

        # Act / Assert: sending on an unopened client must not raise.
        client._send_frame(0x8, b"")

    def test_read_exact_raises_when_not_connected(self):
        # Arrange
        client = ComfyUIWebSocket("ws://127.0.0.1:1/ws", client_id="c")

        # Act / Assert
        with pytest.raises(ComfyUIError, match="not connected"):
            client._read_exact(1)


class TestSecureScheme:
    def test_connect_rejects_when_peer_closes_before_upgrade(self):
        # Arrange: a peer that accepts then closes without answering the upgrade.
        import socket
        from threading import Thread

        listener = socket.create_server(("127.0.0.1", 0))

        def respond():
            connection, _ = listener.accept()
            connection.recv(4096)
            connection.close()
            listener.close()

        thread = Thread(target=respond, daemon=True)
        thread.start()
        client = ComfyUIWebSocket(f"ws://127.0.0.1:{listener.getsockname()[1]}/ws", client_id="c", timeout=5)

        # Act / Assert
        with pytest.raises(ComfyUIError, match="upgrade was rejected"):
            client.connect()
        thread.join(timeout=5)

    def test_wss_wraps_socket_with_tls(self, websocket_server, monkeypatch):
        # Arrange: a fake TLS context records the wrap and returns the raw socket,
        # so the wss code path is exercised without a certificate.
        import ssl

        wrapped = {}

        class FakeContext:
            def wrap_socket(self, connection, server_hostname=None):
                wrapped["hostname"] = server_hostname
                return connection

        monkeypatch.setattr(ssl, "create_default_context", lambda: FakeContext())
        websocket_server.start(lambda connection: None)
        # Point the wss URL at the plain local listener; the fake context skips real TLS.
        wss_url = websocket_server.url.replace("ws://", "wss://")
        client = ComfyUIWebSocket(wss_url, client_id="client-1", timeout=5)

        # Act
        client.connect()

        # Assert: the wss branch wrapped the socket using the URL host for SNI.
        assert wrapped["hostname"] == "127.0.0.1"
        assert websocket_server.request_headers.get("upgrade") == "websocket"
