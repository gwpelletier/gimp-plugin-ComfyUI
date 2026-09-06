"""Validated, collision-safe image export for generation results."""

from __future__ import annotations

import re
from pathlib import Path


class ExportError(RuntimeError):
    """Raised when generated image bytes cannot be safely exported."""


class ImageExporter:
    """Write validated image bytes to a user-selected directory."""

    _safe_name = re.compile(r"[^A-Za-z0-9._-]+")
    _signatures = {
        ".png": (b"\x89PNG\r\n\x1a\n",),
        ".jpg": (b"\xff\xd8\xff",),
        ".jpeg": (b"\xff\xd8\xff",),
        ".gif": (b"GIF87a", b"GIF89a"),
        ".webp": (b"RIFF",),
    }

    def __init__(self, directory: str | Path):
        self.directory = Path(directory).expanduser()
        if self.directory.exists() and not self.directory.is_dir():
            raise ExportError(f"Output path is not a directory: {self.directory}")

    def export(
        self,
        data: bytes,
        source_name: str,
        *,
        index: int = 0,
        overwrite: bool = False,
    ) -> Path:
        """Validate and export bytes, preserving a supported source extension."""
        extension = Path(source_name).suffix.lower()
        if extension not in self._signatures:
            raise ExportError(f"Unsupported image extension: {extension or '<none>'}")
        self._validate_bytes(data, extension)
        self.directory.mkdir(parents=True, exist_ok=True)
        stem = self._safe_name.sub("-", Path(source_name).stem).strip(".-") or "result"
        if index:
            stem = f"{stem}-{index + 1}"
        candidate = self.directory / f"{stem}{extension}"
        if not overwrite:
            candidate = self._available_path(candidate)
        try:
            candidate.write_bytes(data)
        except OSError as error:
            raise ExportError(f"Unable to export image to {candidate}: {error}") from error
        return candidate

    @classmethod
    def _validate_bytes(cls, data: bytes, extension: str) -> None:
        if not data or not any(data.startswith(signature) for signature in cls._signatures[extension]):
            raise ExportError(f"Downloaded content is not a valid {extension} image")
        if extension == ".webp" and data[8:12] != b"WEBP":
            raise ExportError("Downloaded content is not a valid .webp image")

    @staticmethod
    def _available_path(path: Path) -> Path:
        if not path.exists():
            return path
        for suffix in range(2, 10000):
            candidate = path.with_name(f"{path.stem}-{suffix}{path.suffix}")
            if not candidate.exists():
                return candidate
        raise ExportError(f"Unable to find an available filename for {path}")
