"""Minimal RFC 6455 WebSocket server adapter for transport tests."""

from __future__ import annotations

import base64
import hashlib
import socket
import struct
import threading
from threading import Event, Thread

ACCEPT_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class FakeWebSocketServer:
    """Owns a local WebSocket endpoint used at the transport boundary.

    The server completes the HTTP upgrade handshake, then runs a per-test
    scripted exchange so tests assert the client's observable wire behavior
    (parsed events, pong replies, close handling) rather than internals.
    """

    def __init__(self):
        self._listener = socket.create_server(("127.0.0.1", 0))
        self._thread: Thread | None = None
        self._stop = Event()
        self._handshake_done = Event()
        self.connection: socket.socket | None = None
        self.request_line = ""
        self.request_headers: dict[str, str] = {}

    @property
    def url(self) -> str:
        return f"ws://127.0.0.1:{self._listener.getsockname()[1]}/ws"

    def start(self, exchange) -> None:
        """Begin listening; the upgrade runs synchronously in ``accept_upgrade``."""
        self._thread = Thread(target=self._serve, args=(exchange,), daemon=True)
        self._thread.start()

    def accept_upgrade(self, timeout: float = 5.0) -> None:
        """Block until the client's upgrade handshake has completed.

        Tests call ``client.connect()`` first; ``accept_upgrade`` returns once the
        server has answered the upgrade and is running the scripted exchange, so
        the client's first read can never race the server's first frame.
        """
        if not self._handshake_done.wait(timeout=timeout):
            raise TimeoutError("client did not complete the WebSocket upgrade")

    def stop(self) -> None:
        self._stop.set()
        if self.connection is not None:
            try:
                self.connection.close()
            except OSError:
                pass
        self._listener.close()
        # A scripted exchange may call stop() from the server thread itself;
        # a thread cannot join itself.
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=5)

    def _serve(self, exchange) -> None:
        self._listener.settimeout(5)
        try:
            connection, _ = self._listener.accept()
        except (TimeoutError, OSError):
            return
        self.connection = connection
        try:
            if not self._handshake(connection):
                self._handshake_done.set()
                return
            # Signal right after the upgrade so the test's connect() returns and
            # drives the exchange (send or receive) from the main thread.
            self._handshake_done.set()
            if not self._stop.is_set():
                try:
                    exchange(connection)
                except (ConnectionError, OSError):
                    pass
        finally:
            try:
                connection.close()
            except OSError:
                pass

    def _handshake(self, connection: socket.socket) -> bool:
        # Read one byte at a time up to the header terminator so we never
        # over-read into a WebSocket frame the client may have pipelined.
        data = bytearray()
        try:
            while b"\r\n\r\n" not in data:
                chunk = connection.recv(1)
                if not chunk:
                    return False
                data.extend(chunk)
        except OSError:
            return False
        head = bytes(data).decode("latin-1")
        lines = head.split("\r\n")
        self.request_line = lines[0]
        self.request_headers = {
            key.strip().lower(): value.strip()
            for key, _, value in (line.partition(":") for line in lines[1:] if ":" in line)
        }
        key = self.request_headers.get("sec-websocket-key", "")
        accept = base64.b64encode(hashlib.sha1((key + ACCEPT_GUID).encode()).digest()).decode()
        response = (
            "HTTP/1.1 101 Switching Protocols\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Accept: {accept}\r\n\r\n"
        )
        connection.sendall(response.encode("latin-1"))
        return True


def send_server_frame(connection: socket.socket, opcode: int, payload: bytes) -> None:
    """Send an unmasked frame, the only legal server-to-client form."""
    length = len(payload)
    if length < 126:
        header = bytes((0x80 | opcode, length))
    elif length <= 0xFFFF:
        header = bytes((0x80 | opcode, 126)) + struct.pack(">H", length)
    else:
        header = bytes((0x80 | opcode, 127)) + struct.pack(">Q", length)
    connection.sendall(header + payload)


def read_client_frame(connection: socket.socket) -> tuple[int, bytes]:
    """Read one client frame, unmasking it as RFC 6455 requires."""
    first, second = _read_exact(connection, 2)
    opcode = first & 0x0F
    length = second & 0x7F
    if length == 126:
        length = struct.unpack(">H", _read_exact(connection, 2))[0]
    elif length == 127:
        length = struct.unpack(">Q", _read_exact(connection, 8))[0]
    mask = _read_exact(connection, 4) if second & 0x80 else b""
    payload = bytearray(_read_exact(connection, length))
    if mask:
        for index in range(length):
            payload[index] ^= mask[index % 4]
    return opcode, bytes(payload)


def _read_exact(connection: socket.socket, length: int) -> bytes:
    data = bytearray()
    while len(data) < length:
        try:
            chunk = connection.recv(length - len(data))
        except (TimeoutError, OSError) as error:
            raise ConnectionError("timed out reading from peer") from error
        if not chunk:
            raise ConnectionError("peer closed the connection")
        data.extend(chunk)
    return bytes(data)
