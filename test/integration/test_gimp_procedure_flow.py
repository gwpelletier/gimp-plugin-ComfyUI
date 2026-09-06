import os

import pytest

from test.support.gimp_process import GimpProcess


pytestmark = pytest.mark.integration


@pytest.mark.skipif(not os.environ.get("GIMP_BIN"), reason="Set GIMP_BIN to run GIMP integration tests")
class TestGimpProcedureFlow:
    def test_registered_procedure_accepts_real_image_boundary(self, tmp_path):
        # Arrange
        source_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        script_path = tmp_path / "procedure_harness.py"
        script_path.write_text(
            "\n".join((
                "import sys",
                "import gi",
                "gi.require_version('Gimp', '3.0')",
                "from gi.repository import Gimp",
                "pdb = Gimp.get_pdb()",
                "procedure = pdb.lookup_procedure('python-fu-comfyui-generate')",
                "assert procedure is not None",
                "eraser_procedure = pdb.lookup_procedure('python-fu-comfyui-eraser')",
                "assert eraser_procedure is not None",
                "image = Gimp.Image.new(16, 16, Gimp.ImageBaseType.RGB)",
                "config = procedure.create_config()",
                "config.set_property('run-mode', Gimp.RunMode.NONINTERACTIVE)",
                "config.set_property('image', image)",
                "result = procedure.run(config)",
                "assert result.index(0) == Gimp.PDBStatusType.CALLING_ERROR",
                "print('GIMP_PROCEDURE_OK')",
            )),
            encoding="utf-8",
        )
        gimp = GimpProcess(os.environ["GIMP_BIN"])

        # Act
        return_code, output = gimp.run_python(script_path)

        # Assert
        assert return_code == 0, output
        assert "GIMP_PROCEDURE_OK" in output
