import os

import pytest

from test.support.gimp_process import GimpProcess


pytestmark = pytest.mark.integration


@pytest.mark.skipif(not os.environ.get("GIMP_BIN"), reason="Set GIMP_BIN to run GIMP integration tests")
class TestGimpEraserFlow:
    def test_brush_painted_selection_configures_inpainting_dialog(self, tmp_path):
        # Arrange
        source_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        script_path = tmp_path / "eraser_harness.py"
        script_path.write_text(
            "\n".join((
                "import sys",
                "import gi",
                "gi.require_version('Gimp', '3.0')",
                "gi.require_version('GimpUi', '3.0')",
                "from gi.repository import Gimp, GimpUi",
                f"sys.path.insert(0, {os.path.join(source_root, 'src')!r})",
                "from comfyui_plugin.gimp_ui import ComfyUIGenerationDialog",
                "GimpUi.init('gimp-comfyui-eraser-test')",
                "image = Gimp.Image.new(32, 32, Gimp.ImageBaseType.RGB)",
                "Gimp.Image.select_rectangle(image, Gimp.ChannelOps.REPLACE, 4, 4, 12, 12)",
                "dialog = ComfyUIGenerationDialog(image, eraser_mode=True)",
                "assert dialog.workflow_selector.get_active_id().endswith('sdxl-inpainting-api.json')",
                "assert dialog.prompt.get_text().startswith('Remove the selected object')",
                "assert not Gimp.Selection.is_empty(image)",
                "dialog.destroy()",
                "print('GIMP_ERASER_OK')",
            )),
            encoding="utf-8",
        )
        gimp = GimpProcess(os.environ["GIMP_BIN"])

        # Act
        return_code, output = gimp.run_python(script_path)

        # Assert
        assert return_code == 0, output
        assert "GIMP_ERASER_OK" in output