import os

import pytest

from test.support.gimp_process import GimpProcess


pytestmark = pytest.mark.integration


@pytest.mark.skipif(not os.environ.get("GIMP_BIN"), reason="Set GIMP_BIN to run GIMP integration tests")
class TestGimpMaskFlow:
    def test_selection_mask_export_preserves_selection_and_writes_unique_file(self, tmp_path):
        # Arrange
        output_directory = tmp_path / "temporary_images"
        script_path = tmp_path / "mask_harness.py"
        source_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        script_path.write_text(
            "\n".join(
                (
                    "import os",
                    "import sys",
                    "from pathlib import Path",
                    "import gi",
                    "gi.require_version('Gimp', '3.0')",
                    "from gi.repository import Gimp",
                    f"sys.path.insert(0, {os.path.join(source_root, 'src')!r})",
                    "from comfyui_plugin.gimp_image import GimpImageOperations",
                    f"output_directory = Path({str(output_directory)!r})",
                    "image = Gimp.Image.new(32, 32, Gimp.ImageBaseType.RGB)",
                    "Gimp.Image.select_rectangle(image, Gimp.ChannelOps.REPLACE, 4, 4, 12, 12)",
                    "result = GimpImageOperations().create_mask(image, output_directory)",
                    "assert result is not None and result.is_file()",
                    "assert not Gimp.Selection.is_empty(image)",
                    "matches = list(output_directory.glob('mask-*.png'))",
                    "assert matches == [result]",
                    "layer = Gimp.Layer.new(image, 'Result', 32, 32, Gimp.ImageType.RGBA_IMAGE, 100, Gimp.LayerMode.NORMAL)",
                    "image.insert_layer(layer, None, 0)",
                    "operations = GimpImageOperations()",
                    "operations.attach_generation_metadata(layer, {'workflow_path': 'workflow.json', 'prompt_id': 'job-1', 'seed': 42})",
                    "assert operations.read_generation_metadata(layer) == {'workflow_path': 'workflow.json', 'prompt_id': 'job-1', 'seed': 42}",
                    "print('MASK_FLOW_OK')",
                )
            ),
            encoding="utf-8",
        )

        # Act
        return_code, output = GimpProcess(os.environ["GIMP_BIN"]).run_python(script_path)

        # Assert
        assert return_code == 0, output
        assert "MASK_FLOW_OK" in output