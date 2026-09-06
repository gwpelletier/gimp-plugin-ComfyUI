"""GIMP 3 image operations kept at the GIMP integration boundary."""

from __future__ import annotations

import uuid
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

    def read_generation_metadata(self, layer: Gimp.Layer) -> dict[str, Any] | None:
        """Read the versioned generation metadata parasite from a layer."""
        import json

        parasite = layer.get_parasite("comfy-data-v1")
        if parasite is None:
            return None
        try:
            data = json.loads(bytes(parasite.get_data()).decode("utf-8"))
        except (TypeError, ValueError, UnicodeDecodeError) as error:
            raise GimpImageError("Generation metadata parasite is invalid") from error
        if not isinstance(data, dict):
            raise GimpImageError("Generation metadata must be a JSON object")
        return data

    def create_mask(self, image: Gimp.Image, path: str | Path) -> Path | None:
        """Export the current selection as a unique grayscale mask file.

        The source image, selection, and GIMP context are left unchanged. The
        supplied path is treated as the per-user temporary image directory.
        """
        if Gimp.Selection.is_empty(image):
            return None

        output_directory = Path(path)
        output_directory.mkdir(parents=True, exist_ok=True)
        output_path = output_directory / f"mask-{uuid.uuid4().hex}.png"
        temporary_image = None
        Gimp.context_push()
        try:
            temporary_image = image.duplicate()
            saved_selection = Gimp.Selection.save(temporary_image)
            if saved_selection is None:
                raise GimpImageError("Unable to save the current selection")
            mask_layer = Gimp.Layer.new(
                temporary_image,
                "Mask",
                temporary_image.get_width(),
                temporary_image.get_height(),
                Gimp.ImageType.RGBA_IMAGE,
                100,
                Gimp.LayerMode.NORMAL,
            )
            temporary_image.insert_layer(mask_layer, None, 0)
            Gimp.Selection.none(temporary_image)
            Gimp.context_set_default_colors()
            mask_layer.edit_fill(Gimp.FillType.FOREGROUND)
            temporary_image.select_item(Gimp.ChannelOps.REPLACE, saved_selection)
            Gimp.context_swap_colors()
            mask_layer.edit_fill(Gimp.FillType.FOREGROUND)
            self.save_image(temporary_image, output_path)
            return output_path
        except Exception as error:
            if isinstance(error, GimpImageError):
                raise
            raise GimpImageError(f"Unable to create selection mask: {error}") from error
        finally:
            Gimp.context_pop()
            if temporary_image is not None:
                temporary_image.delete()