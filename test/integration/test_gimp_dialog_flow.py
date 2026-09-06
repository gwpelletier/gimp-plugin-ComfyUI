import os

import pytest

from test.support.gimp_process import GimpProcess


pytestmark = pytest.mark.integration


@pytest.mark.skipif(not os.environ.get("GIMP_BIN"), reason="Set GIMP_BIN to run GIMP integration tests")
class TestGimpDialogFlow:
    def test_interactive_dialog_constructs_after_gimp_ui_init(self, tmp_path):
        # Arrange
        source_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        script_path = tmp_path / "dialog_harness.py"
        script_path.write_text(
            "\n".join((
                "import sys",
                "import gi",
                "gi.require_version('Gimp', '3.0')",
                "gi.require_version('GimpUi', '3.0')",
                "from gi.repository import GimpUi",
                f"sys.path.insert(0, {os.path.join(source_root, 'src')!r})",
                "from comfyui_plugin.gimp_ui import ComfyUIGenerationDialog",
                "GimpUi.init('gimp-comfyui-test')",
                "dialog = ComfyUIGenerationDialog(None)",
                "assert dialog.vae is not None",
                "dialog.destroy()",
                "print('GIMP_DIALOG_OK')",
            )),
            encoding="utf-8",
        )
        gimp = GimpProcess(os.environ["GIMP_BIN"])

        # Act
        return_code, output = gimp.run_python(script_path)

        # Assert
        assert return_code == 0, output
        assert "GIMP_DIALOG_OK" in output
