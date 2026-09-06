import os

import pytest

from test.support.gimp_process import GimpProcess


pytestmark = pytest.mark.integration


@pytest.mark.skipif(not os.environ.get("GIMP_BIN"), reason="Set GIMP_BIN to run GIMP integration tests")
class TestGimpWorkflowRegistryFlow:
    def test_registry_selection_survives_separate_gimp_processes(self, tmp_path):
        # Arrange
        registry_path = tmp_path / "workflows.json"
        workflow_path = tmp_path / "imported.json"
        workflow_path.write_text('{"1": {"class_type": "KSampler", "inputs": {}}}', encoding="utf-8")
        source_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        first_script = tmp_path / "registry_write.py"
        first_script.write_text(
            "\n".join((
                "import sys",
                f"sys.path.insert(0, {os.path.join(source_root, 'src')!r})",
                "from pathlib import Path",
                "from comfyui_plugin.storage import WorkflowRegistry",
                f"registry = WorkflowRegistry(Path({str(registry_path)!r}))",
                f"workflow = Path({str(workflow_path)!r})",
                "assert registry.add([workflow]) == 1",
                "registry.select(workflow)",
            )),
            encoding="utf-8",
        )
        second_script = tmp_path / "registry_read.py"
        second_script.write_text(
            "\n".join((
                "import sys",
                f"sys.path.insert(0, {os.path.join(source_root, 'src')!r})",
                "from pathlib import Path",
                "from comfyui_plugin.storage import WorkflowRegistry",
                f"registry = WorkflowRegistry(Path({str(registry_path)!r}))",
                f"assert registry.selected_path == str(Path({str(workflow_path)!r}).resolve())",
                "print('WORKFLOW_REGISTRY_OK')",
            )),
            encoding="utf-8",
        )
        gimp = GimpProcess(os.environ["GIMP_BIN"])

        # Act
        first_code, first_output = gimp.run_python(first_script)
        second_code, second_output = gimp.run_python(second_script)

        # Assert
        assert first_code == 0, first_output
        assert second_code == 0, second_output
        assert "WORKFLOW_REGISTRY_OK" in second_output