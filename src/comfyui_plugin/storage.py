"""Persistent settings and workflow registry for the plug-in."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class StorageError(RuntimeError):
    """Raised when persistent plug-in data cannot be read or written."""


@dataclass(frozen=True)
class PluginPaths:
    """User data paths supplied by the GIMP-facing boundary.

    Args:
        root: Per-user plug-in data directory.
    """

    root: Path

    @property
    def workflows(self) -> Path:
        return self.root / "workflows"

    @property
    def temporary_images(self) -> Path:
        return self.root / "temporary_images"

    @property
    def settings_file(self) -> Path:
        return self.root / "settings.json"

    @property
    def prompt_history(self) -> Path:
        return self.root / "prompt-history.json"

    @property
    def styles(self) -> Path:
        return self.root / "styles"

    @property
    def workflow_registry(self) -> Path:
        return self.workflows / "workflows.json"

    def ensure(self) -> None:
        """Create the plug-in data directories if they do not exist."""
        self.root.mkdir(parents=True, exist_ok=True)
        self.workflows.mkdir(parents=True, exist_ok=True)
        self.temporary_images.mkdir(parents=True, exist_ok=True)
        self.styles.mkdir(parents=True, exist_ok=True)


class JsonStore:
    """Read and atomically write JSON objects at a known user-data path."""

    def __init__(self, path: Path):
        """Create a JSON store rooted at ``path``."""
        self.path = path

    def load(self) -> dict[str, Any]:
        """Load a JSON object, returning an empty object for a new store."""
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise StorageError(f"Unable to read {self.path}: {error}") from error
        if not isinstance(data, dict):
            raise StorageError(f"Expected a JSON object in {self.path}")
        return data

    def save(self, data: dict[str, Any]) -> None:
        """Atomically replace the store with ``data``."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        try:
            temporary_path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
            os.replace(temporary_path, self.path)
        except OSError as error:
            temporary_path.unlink(missing_ok=True)
            raise StorageError(f"Unable to write {self.path}: {error}") from error


class WorkflowRegistry:
    """Manage user-imported ComfyUI workflow file references."""

    def __init__(self, path: Path):
        """Create a registry backed by a JSON file."""
        self.store = JsonStore(path)

    def list(self) -> list[dict[str, str]]:
        """Return registered workflow file references."""
        workflows = self.store.load().get("workflows", [])
        if not isinstance(workflows, list):
            raise StorageError(f"Invalid workflow registry: {self.store.path}")
        return [item for item in workflows if isinstance(item, dict)]

    @property
    def selected_path(self) -> str | None:
        """Return the persisted selected workflow path, if it is registered."""
        selected = self.store.load().get("selected_path")
        if not isinstance(selected, str):
            return None
        return selected if any(item.get("path") == selected for item in self.list()) else None

    def add(self, paths: list[str | Path]) -> int:
        """Register new JSON workflow paths and return the number added."""
        workflows = self.list()
        existing = {item.get("path") for item in workflows}
        additions = []
        for source_path in paths:
            path = Path(source_path).expanduser().resolve()
            if not path.is_file() or path.suffix.lower() != ".json" or str(path) in existing:
                continue
            additions.append({"path": str(path), "title": path.stem})
            existing.add(str(path))
        if additions:
            self.store.save({"workflows": workflows + additions})
        return len(additions)

    def select(self, path: str | Path | None) -> None:
        """Persist a registered workflow as the next selected entry."""
        workflows = self.list()
        selected_path = None if path is None else str(Path(path).expanduser().resolve())
        if selected_path is not None and not any(item.get("path") == selected_path for item in workflows):
            raise StorageError(f"Workflow is not registered: {selected_path}")
        self.store.save({"workflows": workflows, "selected_path": selected_path})

    def remove(self, path: str | Path) -> bool:
        """Remove one resolved workflow path and report whether it existed."""
        target = str(Path(path).expanduser().resolve())
        workflows = self.list()
        remaining = [item for item in workflows if item.get("path") != target]
        if len(remaining) == len(workflows):
            return False
        selected_path = self.selected_path
        self.store.save({
            "workflows": remaining,
            "selected_path": None if selected_path == target else selected_path,
        })
        return True


class PromptHistory:
    """Persist recent prompt and generation settings with bounded retention."""

    def __init__(self, path: Path, *, limit: int = 50):
        if limit < 1:
            raise ValueError("History limit must be positive")
        self.store = JsonStore(path)
        self.limit = limit

    def list(self) -> list[dict[str, Any]]:
        """Return recent history entries, newest first."""
        entries = self.store.load().get("entries", [])
        if not isinstance(entries, list) or any(not isinstance(item, dict) for item in entries):
            raise StorageError(f"Invalid prompt history: {self.store.path}")
        return entries[: self.limit]

    def add(self, entry: dict[str, Any]) -> None:
        """Add an entry, moving an identical entry to the front."""
        if not isinstance(entry, dict):
            raise StorageError("Prompt history entries must be JSON objects")
        entries = [item for item in self.list() if item != entry]
        self.store.save({"entries": [entry, *entries[: self.limit - 1]]})

    def delete(self, index: int) -> bool:
        """Delete an entry by its current list index."""
        entries = self.list()
        if index < 0 or index >= len(entries):
            return False
        del entries[index]
        self.store.save({"entries": entries})
        return True


class StylePresetStore:
    """Store named generation presets as sanitized JSON filenames."""

    _safe_name = re.compile(r"[^A-Za-z0-9._-]+")

    def __init__(self, directory: Path):
        self.directory = directory

    def list(self) -> list[str]:
        """Return available preset names in stable order."""
        if not self.directory.exists():
            return []
        return sorted(path.stem for path in self.directory.glob("*.json") if path.is_file())

    def save(self, name: str, settings: dict[str, Any]) -> str:
        """Save a preset and return its sanitized unique name."""
        safe_name = self._sanitize_name(name)
        path = self.directory / f"{safe_name}.json"
        self.directory.mkdir(parents=True, exist_ok=True)
        JsonStore(path).save(settings)
        return safe_name

    def load(self, name: str) -> dict[str, Any]:
        """Load a preset by name."""
        return JsonStore(self._path_for(name)).load()

    def delete(self, name: str) -> bool:
        """Delete a preset without affecting other presets."""
        path = self._path_for(name)
        try:
            path.unlink()
        except FileNotFoundError:
            return False
        except OSError as error:
            raise StorageError(f"Unable to delete {path}: {error}") from error
        return True

    def _path_for(self, name: str) -> Path:
        safe_name = self._sanitize_name(name)
        path = (self.directory / f"{safe_name}.json").resolve()
        if path.parent != self.directory.resolve():
            raise StorageError("Style name resolves outside the styles directory")
        return path

    @classmethod
    def _sanitize_name(cls, name: str) -> str:
        safe_name = cls._safe_name.sub("-", name.strip()).strip(".-")
        if not safe_name:
            raise StorageError("Style name must contain a safe filename character")
        return safe_name[:100]