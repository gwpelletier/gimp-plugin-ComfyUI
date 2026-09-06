import os

import pytest

from test.support.gimp_process import GimpProcess


pytestmark = pytest.mark.integration


@pytest.mark.skipif(not os.environ.get("GIMP_BIN"), reason="Set GIMP_BIN to run GIMP integration tests")
class TestGimpExportFlow:
    def test_exported_image_can_be_reopened_by_gimp(self, tmp_path):
        # Arrange
        source_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        source_image = os.path.join(source_root, "test", "fixtures", "priority-1", "source.png")
        script_path = tmp_path / "export_harness.py"
        output_directory = tmp_path / "exports"
        script_path.write_text(
            "\n".join((
                "import os",
                "import sys",
                "from pathlib import Path",
                "import gi",
                "gi.require_version('Gimp', '3.0')",
                "from gi.repository import Gimp",
                f"sys.path.insert(0, {os.path.join(source_root, 'src')!r})",
                "from comfyui_plugin.export import ImageExporter",
                "from comfyui_plugin.gimp_image import GimpImageOperations",
                f"source = Path({source_image!r})",
                f"target = Path({str(output_directory)!r})",
                "exported = ImageExporter(target).export(source.read_bytes(), source.name)",
                "image = GimpImageOperations().load_result(exported)",
                "assert image is not None",
                "print('GIMP_EXPORT_OK')",
            )),
            encoding="utf-8",
        )
        gimp = GimpProcess(os.environ["GIMP_BIN"])

        # Act
        return_code, output = gimp.run_python(script_path)

        # Assert
        assert return_code == 0, output
        assert "GIMP_EXPORT_OK" in output
