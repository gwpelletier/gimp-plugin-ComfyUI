"""Minimal standard-library WebSocket transport for ComfyUI events."""

from __future__ import annotations

import base64
import hashlib
import os
import socket
import ssl
import struct
from dataclasses import dataclass
from urllib.parse import ParseResult, parse_qsl, urlencode, urlparse, urlunparse

from .client import ComfyUIError, ComfyUIEvent, parse_websocket_event


@dataclass(frozen=True)
class ComfyUIPreview:
    """Binary preview payload received from ComfyUI."""

    image_format: int
    data: bytes


class ComfyUIWebSocket:
    """Receive ComfyUI JSON events and binary previews over WebSocket."""

    def __init__(self, url: str, *, client_id: str, timeout: float = 30.0):
        parsed = urlparse(url)
        if parsed.scheme not in {"ws", "wss"}:
            raise ValueError("WebSocket URL must use ws:// or wss://")
        self.url = self._with_client_id(parsed, client_id)
        self.timeout = timeout
        self._socket: socket.socket | None = None

    def connect(self) -> None:
        """Open the socket and validate the HTTP upgrade response."""
        parsed = urlparse(self.url)
        port = parsed.port or (443 if parsed.scheme == "wss" else 80)
        connection = socket.create_connection((parsed.hostname, port), self.timeout)
        if parsed.scheme == "wss":
            context = ssl.create_default_context()
            connection = context.wrap_socket(connection, server_hostname=parsed.hostname)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        path = urlunparse(ParseResult("", "", parsed.path or "/", "", parsed.query, ""))
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {parsed.hostname}:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        ).encode("ascii")
        connection.sendall(request)
        response = self._read_http_headers(connection)
        expected = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()
        lowered_response = response.lower()
        expected_header = f"sec-websocket-accept: {expected}".encode().lower()
        if b" 101 " not in response or expected_header not in lowered_response:
            connection.close()
            raise ComfyUIError("ComfyUI WebSocket upgrade was rejected")
        self._socket = connection

    def receive(self) -> ComfyUIEvent | ComfyUIPreview | None:
        """Receive one event or preview, returning ``None`` for ignored frames."""
        if self._socket is None:
            raise ComfyUIError("ComfyUI WebSocket is not connected")
        opcode, payload = self._read_frame()
        if opcode == 0x1:
            return parse_websocket_event(payload)
        if opcode == 0x2:
            if len(payload) < 8:
                return None
            image_format = struct.unpack(">I", payload[4:8])[0]
            return ComfyUIPreview(image_format, payload[8:])
        if opcode == 0x9:
            self._send_frame(0xA, payload)
            return None
        if opcode == 0x8:
            self.close()
            return None
        return None

    def close(self) -> None:
        """Close the socket and discard any preview bytes."""
        if self._socket is not None:
            try:
                self._send_frame(0x8, b"")
            except OSError:
                pass
            self._socket.close()
            self._socket = None

    def _read_frame(self) -> tuple[int, bytes]:
        first, second = self._read_exact(2)
        opcode = first & 0x0F
        length = second & 0x7F
        if length == 126:
            length = struct.unpack(">H", self._read_exact(2))[0]
        elif length == 127:
            length = struct.unpack(">Q", self._read_exact(8))[0]
        masked = second & 0x80
        mask = self._read_exact(4) if masked else b""
        payload = bytearray(self._read_exact(length))
        if masked:
            for index in range(length):
                payload[index] ^= mask[index % 4]
        return opcode, bytes(payload)

    def _send_frame(self, opcode: int, payload: bytes) -> None:
        if self._socket is None:
            return
        mask = os.urandom(4)
        masked_payload = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
        length = len(payload)
        if length < 126:
            header = bytes((0x80 | opcode, 0x80 | length))
        elif length <= 0xFFFF:
            header = bytes((0x80 | opcode, 0xFE)) + struct.pack(">H", length)
        else:
            header = bytes((0x80 | opcode, 0xFF)) + struct.pack(">Q", length)
        self._socket.sendall(header + mask + masked_payload)

    def _read_exact(self, length: int) -> bytes:
        if self._socket is None:
            raise ComfyUIError("ComfyUI WebSocket is not connected")
        data = bytearray()
        while len(data) < length:
            chunk = self._socket.recv(length - len(data))
            if not chunk:
                raise ComfyUIError("ComfyUI WebSocket closed unexpectedly")
            data.extend(chunk)
        return bytes(data)

    @staticmethod
    def _read_http_headers(connection: socket.socket) -> bytes:
        # Read one byte at a time so the upgrade response never over-reads into
        # the first WebSocket frame, which can share the same TCP segment.
        data = bytearray()
        while b"\r\n\r\n" not in data:
            chunk = connection.recv(1)
            if not chunk:
                break
            data.extend(chunk)
        return bytes(data)

    @staticmethod
    def _with_client_id(parsed, client_id: str) -> str:
        query = dict(parse_qsl(parsed.query))
        query["clientId"] = client_id
        return urlunparse(parsed._replace(query=urlencode(query)))
