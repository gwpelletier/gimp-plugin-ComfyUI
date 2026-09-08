from pathlib import Path

import pytest

from comfyui_plugin.export import ExportError, ImageExporter


PNG = b"\x89PNG\r\n\x1a\nimage"


class TestImageExporter:
    def test_preserves_extension_and_adds_collision_suffix(self, tmp_path):
        # Arrange
        exporter = ImageExporter(tmp_path)

        # Act
        first = exporter.export(PNG, "source image.png")
        second = exporter.export(PNG, "source image.png")

        # Assert
        assert first.name == "source-image.png"
        assert second.name == "source-image-2.png"
        assert first.read_bytes() == PNG

    def test_overwrite_is_explicit(self, tmp_path):
        # Arrange
        exporter = ImageExporter(tmp_path)
        exporter.export(PNG, "result.png")

        # Act
        exported = exporter.export(PNG, "result.png", overwrite=True)

        # Assert
        assert exported.name == "result.png"

    def test_rejects_invalid_content_and_extension(self, tmp_path):
        # Arrange
        exporter = ImageExporter(tmp_path)

        # Act
        with pytest.raises(ExportError, match="valid .png"):
            exporter.export(b"not an image", "result.png")
        with pytest.raises(ExportError, match="Unsupported image extension"):
            exporter.export(PNG, "result.bmp")

    def test_rejects_file_as_output_directory(self, tmp_path):
        # Arrange
        output_path = tmp_path / "output"
        output_path.write_text("not a directory", encoding="utf-8")

        # Act
        with pytest.raises(ExportError, match="not a directory"):
            ImageExporter(output_path)

    def test_export_with_index_offsets_stem_by_position(self, tmp_path):
        # Arrange
        exporter = ImageExporter(tmp_path)

        # Act
        exported = exporter.export(PNG, "result.png", index=2)

        # Assert
        assert exported.name == "result-3.png"
        assert exported.read_bytes() == PNG

    def test_export_wraps_write_errors_in_export_error(self, tmp_path):
        # Arrange
        exporter = ImageExporter(tmp_path)
        (tmp_path / "result.png").mkdir()

        # Act
        with pytest.raises(ExportError, match="Unable to export image") as exc_info:
            exporter.export(PNG, "result.png", overwrite=True)

        # Assert
        assert isinstance(exc_info.value.__cause__, OSError)

    def test_export_rejects_riff_payload_without_webp_marker(self, tmp_path):
        # Arrange
        exporter = ImageExporter(tmp_path)
        riff_without_marker = b"RIFF\x04\x00\x00\x00NOPE"

        # Act / Assert
        with pytest.raises(ExportError, match="not a valid .webp image"):
            exporter.export(riff_without_marker, "result.webp")

    def test_export_skips_occupied_collision_suffixes(self, tmp_path):
        # Arrange
        exporter = ImageExporter(tmp_path)
        (tmp_path / "result.png").write_bytes(b"first")
        (tmp_path / "result-2.png").write_bytes(b"second")

        # Act
        exported = exporter.export(PNG, "result.png")

        # Assert
        assert exported.name == "result-3.png"
        assert exported.read_bytes() == PNG
        assert (tmp_path / "result-2.png").read_bytes() == b"second"

    def test_export_raises_export_error_when_no_filename_is_available(self, tmp_path, monkeypatch):
        # Arrange
        exporter = ImageExporter(tmp_path)
        monkeypatch.setattr(Path, "exists", lambda self, **_kwargs: True)

        # Act / Assert
        with pytest.raises(ExportError, match="Unable to find an available filename"):
            exporter.export(PNG, "result.png")
