"""Small standard-library ComfyUI API client.

The client deliberately does not import GIMP or GTK so it can run in unit tests
and in a worker thread owned by the plug-in.

Its supported endpoint set is adapted from the GPL-3.0-only ``gimp-comfy-tools``
client and implemented here without copying its vendored dependencies.
"""

from __future__ import annotations

import json
import mimetypes
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class ComfyUIError(RuntimeError):
    """Raised when ComfyUI cannot accept or complete a request."""


class ComfyUICancelledError(ComfyUIError):
    """Raised when a queued ComfyUI prompt is cancelled by the caller."""


@dataclass(frozen=True)
class ComfyImage:
    """Reference to an image stored by ComfyUI."""

    filename: str
    subfolder: str
    folder_type: str


@dataclass(frozen=True)
class ComfyUpload:
    """Reference returned after uploading an image to ComfyUI."""

    filename: str
    subfolder: str
    folder_type: str = "input"


class ComfyUIClient:
    """HTTP client for ComfyUI's queue, history, and view endpoints."""

    def __init__(self, base_url: str, *, timeout: float = 30.0, client_id: str | None = None) -> None:
        """Create a client for a ComfyUI HTTP endpoint.

        Args:
            base_url: HTTP or HTTPS endpoint, with or without a trailing slash.
            timeout: Per-request timeout in seconds.
            client_id: Optional identifier used when queueing prompts.
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.client_id = client_id or str(uuid.uuid4())
        self._object_info_cache: dict | None = None

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
        """Return whether ComfyUI responds to its system endpoint."""
        try:
            self._request("GET", "/system_stats")
        except ComfyUIError:
            return False
        return True

    def get_system_stats(self) -> dict:
        """Return ComfyUI runtime and hardware information.

        Raises:
            ComfyUIError: If the endpoint is unreachable or returns invalid JSON.
        """
        return self._json_request("GET", "/system_stats")

    def interrupt(self) -> dict:
        """Interrupt the currently executing ComfyUI prompt.

        Raises:
            ComfyUIError: If ComfyUI rejects or cannot receive the request.
        """
        return self._json_request("POST", "/interrupt", b"{}", "application/json")

    def clear_queue(self) -> None:
        """Clear prompts waiting in the ComfyUI queue.

        Raises:
            ComfyUIError: If ComfyUI rejects or cannot receive the request.
        """
        payload = json.dumps({"clear": True}).encode()
        self._json_request("POST", "/queue", payload, "application/json")

    def get_object_info(self, *, refresh: bool = False) -> dict:
        """Return cached or freshly fetched ComfyUI node schemas.

        Args:
            refresh: Refetch schemas instead of using the local cache.
        """
        if self._object_info_cache is None or refresh:
            self._object_info_cache = self._json_request("GET", "/object_info")
        return self._object_info_cache

    def get_node_input_options(self, node_class: str, input_name: str) -> list:
        """Return enumerated options for one ComfyUI node input.

        Missing node or input definitions return an empty list.
        """
        try:
            node_info = self.get_object_info()[node_class]
            return node_info["input"]["required"][input_name][0]
        except (KeyError, TypeError):
            return []

    def get_available_checkpoints(self) -> list[str]:
        """Return checkpoint names advertised by the ComfyUI node schema."""
        return self.get_node_input_options("CheckpointLoaderSimple", "ckpt_name")

    def get_available_loras(self) -> list[str]:
        """Return LoRA names advertised by the ComfyUI node schema."""
        return self.get_node_input_options("LoraLoader", "lora_name")

    def get_available_vaes(self) -> list[str]:
        """Return VAE names advertised by the ComfyUI node schema."""
        return self.get_node_input_options("VAELoader", "vae_name")

    def get_available_samplers(self) -> list[str]:
        """Return sampler names advertised by the ComfyUI node schema."""
        return self.get_node_input_options("KSampler", "sampler_name")

    def get_available_schedulers(self) -> list[str]:
        """Return scheduler names advertised by the ComfyUI node schema."""
        return self.get_node_input_options("KSampler", "scheduler")

    def queue_prompt(self, workflow: dict) -> str:
        """Queue an API-format workflow and return its prompt identifier.

        Raises:
            ComfyUIError: If ComfyUI rejects the workflow or returns an invalid response.
        """
        payload = json.dumps({"prompt": workflow, "client_id": self.client_id}).encode()
        response = json.loads(self._request("POST", "/prompt", payload, "application/json"))
        if response.get("error") or "prompt_id" not in response:
            raise ComfyUIError(f"ComfyUI rejected workflow: {response}")
        return str(response["prompt_id"])

    def upload_image(self, file_path: str, *, subfolder: str = "", overwrite: bool = True) -> ComfyUpload:
        """Upload an image to ComfyUI's input directory.

        Args:
            file_path: Local image path to upload.
            subfolder: ComfyUI input subfolder for the uploaded file.
            overwrite: Whether an existing file with the same name may be replaced.

        Raises:
            ComfyUIError: If the local file is missing or the upload fails.
        """
        path = os.fspath(file_path)
        filename = os.path.basename(path)
        if not os.path.isfile(path):
            raise ComfyUIError(f"Input image does not exist: {path}")

        boundary = f"----GimpComfyUI{uuid.uuid4().hex}"
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        fields = {
            "subfolder": subfolder,
            "overwrite": str(overwrite).lower(),
        }
        parts = []
        for key, value in fields.items():
            parts.extend((
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode(),
                str(value).encode(),
                b"\r\n",
            ))
        parts.extend((
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="image"; filename="{filename}"\r\n'.encode(),
            f"Content-Type: {content_type}\r\n\r\n".encode(),
            Path(path).read_bytes(),
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ))
        response = self._json_request(
            "POST",
            "/upload/image",
            b"".join(parts),
            f"multipart/form-data; boundary={boundary}",
        )
        return ComfyUpload(
            filename=str(response.get("name", filename)),
            subfolder=str(response.get("subfolder", subfolder)),
            folder_type=str(response.get("type", "input")),
        )

    def wait_for_outputs(
        self,
        prompt_id: str,
        *,
        poll_interval: float = 0.5,
        timeout: float = 3600.0,
        cancellation_event: Event | None = None,
    ) -> list[ComfyImage]:
        """Wait for a prompt to finish and return image output references.

        Raises:
            ComfyUIError: If execution fails or the timeout expires.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if cancellation_event is not None and cancellation_event.is_set():
                raise ComfyUICancelledError(f"ComfyUI prompt {prompt_id} was cancelled")
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
        if cancellation_event is not None and cancellation_event.is_set():
            raise ComfyUICancelledError(f"ComfyUI prompt {prompt_id} was cancelled")
        raise ComfyUIError(f"Timed out waiting for ComfyUI workflow {prompt_id}")

    def view_image(self, image: ComfyImage) -> bytes:
        """Download the bytes referenced by a ComfyUI image result."""
        query = urlencode({"filename": image.filename, "subfolder": image.subfolder, "type": image.folder_type})
        return self._request("GET", f"/view?{query}")

    def _json_request(
        self,
        method: str,
        path: str,
        body: bytes | None = None,
        content_type: str | None = None,
    ) -> dict:
        response = self._request(method, path, body, content_type)
        try:
            decoded = json.loads(response)
        except json.JSONDecodeError as error:
            raise ComfyUIError(f"ComfyUI returned invalid JSON for {method} {path}") from error
        if not isinstance(decoded, dict):
            raise ComfyUIError(f"ComfyUI returned a non-object response for {method} {path}")
        return decoded