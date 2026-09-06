import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread


class FakeComfyUIHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"prompt_id": "job-1"}).encode())

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(self._response_body()).encode())

    def _response_body(self):
        if self.path.startswith("/history"):
            return {"job-1": {"outputs": {"node": {"images": [{"filename": "result.png"}]}}}}
        return {"system": "ok"}

    def log_message(self, *_):
        pass


class FakeComfyUIServer:
    """Owns the fake HTTP process used at the ComfyUI client boundary."""

    def __init__(self):
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), FakeComfyUIHandler)
        self._thread = Thread(target=self._server.serve_forever, daemon=True)

    @property
    def url(self):
        return f"http://127.0.0.1:{self._server.server_port}"

    def start(self):
        self._thread.start()

    def stop(self):
        self._server.shutdown()
        self._server.server_close()