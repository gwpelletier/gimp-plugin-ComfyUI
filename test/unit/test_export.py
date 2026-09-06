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
