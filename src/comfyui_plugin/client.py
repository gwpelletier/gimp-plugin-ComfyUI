"""Small standard-library ComfyUI API client.

The client deliberately does not import GIMP or GTK so it can run in unit tests
and in a worker thread owned by the plug-in.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class ComfyUIError(RuntimeError):
    """Raised when ComfyUI cannot accept or complete a request."""


@dataclass(frozen=True)
class ComfyImage:
    filename: str
    subfolder: str
    folder_type: str


class ComfyUIClient:
    """HTTP client for ComfyUI's queue, history, and view endpoints."""

    def __init__(self, base_url: str, *, timeout: float = 30.0, client_id: str | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.client_id = client_id or str(uuid.uuid4())

    def _request(self, method: str, path: str, body: bytes | None = None, content_type: str | None = None) -> bytes:
        headers = {"Accept": "application/json"}
        if content_type:
            headers["Content-Type"] = content_type
        request = Request(f"{self.base_url}{path}", data=body, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return response.read()
        except (HTTPError, URLError, TimeoutError) as error:
            raise ComfyUIError(f"ComfyUI request failed: {method} {path}: {error}") from error

    def health_check(self) -> bool:
        try:
            self._request("GET", "/system_stats")
        except ComfyUIError:
            return False
        return True

    def queue_prompt(self, workflow: dict) -> str:
        payload = json.dumps({"prompt": workflow, "client_id": self.client_id}).encode()
        response = json.loads(self._request("POST", "/prompt", payload, "application/json"))
        if response.get("error") or "prompt_id" not in response:
            raise ComfyUIError(f"ComfyUI rejected workflow: {response}")
        return str(response["prompt_id"])

    def wait_for_outputs(self, prompt_id: str, *, poll_interval: float = 0.5, timeout: float = 3600.0) -> list[ComfyImage]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            history = json.loads(self._request("GET", f"/history/{prompt_id}"))
            prompt = history.get(prompt_id)
            if prompt and prompt.get("status", {}).get("status_str") == "error":
                raise ComfyUIError(f"ComfyUI failed workflow {prompt_id}: {prompt['status']}")
            if prompt and prompt.get("outputs"):
                return [
                    ComfyImage(item["filename"], item.get("subfolder", ""), item.get("type", "output"))
                    for output in prompt["outputs"].values()
                    for item in output.get("images", [])
                ]
            time.sleep(poll_interval)
        raise ComfyUIError(f"Timed out waiting for ComfyUI workflow {prompt_id}")

    def view_image(self, image: ComfyImage) -> bytes:
        query = urlencode({"filename": image.filename, "subfolder": image.subfolder, "type": image.folder_type})
        return self._request("GET", f"/view?{query}")