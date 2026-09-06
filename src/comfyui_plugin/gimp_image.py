"""GIMP 3 image operations kept at the GIMP integration boundary."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import gi

gi.require_version("Gimp", "3.0")
from gi.repository import Gimp, Gio


class GimpImageError(RuntimeError):
    """Raised when a GIMP image operation cannot be completed."""


class GimpImageOperations:
    """Adapt GIMP image data to files and generated result layers."""

    def save_image(self, image: Gimp.Image, path: str | Path) -> Path:
        """Save an image through GIMP's noninteractive file API."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        Gimp.file_save(Gimp.RunMode.NONINTERACTIVE, image, Gio.File.new_for_path(str(target)))
        return target

    def insert_layer(self, image: Gimp.Image, path: str | Path, name: str) -> Gimp.Layer:
        """Load a generated image file and insert it at the top of an image."""
        target = Path(path)
        if not target.is_file():
            raise GimpImageError(f"Generated image does not exist: {target}")
        layer = Gimp.file_load_layer(Gimp.RunMode.NONINTERACTIVE, image, Gio.File.new_for_path(str(target)))
        if layer is None:
            raise GimpImageError(f"Unable to load generated layer from {target}")
        layer.set_name(name)
        image.insert_layer(layer, None, 0)
        return layer

    def load_result(self, path: str | Path) -> Gimp.Image:
        """Open a generated image as a new GIMP image."""
        target = Path(path)
        if not target.is_file():
            raise GimpImageError(f"Generated image does not exist: {target}")
        return Gimp.file_load(Gimp.RunMode.NONINTERACTIVE, Gio.File.new_for_path(str(target)))

    def attach_generation_metadata(self, layer: Gimp.Layer, metadata: dict[str, Any]) -> None:
        """Attach generation settings to a result layer as a GIMP parasite."""
        import json

        parasite = Gimp.Parasite.new("comfy-data-v1", 1, json.dumps(metadata, indent=2).encode("utf-8"))
        layer.attach_parasite(parasite)

    def create_mask(self, image: Gimp.Image, path: str | Path) -> Path | None:
        """Export the current selection as a grayscale mask when one exists."""
        if Gimp.Selection.is_empty(image):
            return None
        raise NotImplementedError("Selection mask export will be added with the interactive generation dialog")