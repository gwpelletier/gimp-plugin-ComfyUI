import os

import pytest

from test.support.gimp_process import GimpProcess


pytestmark = pytest.mark.integration


@pytest.mark.skipif(not os.environ.get("GIMP_BIN"), reason="Set GIMP_BIN to run GIMP integration tests")
class TestPromptHistoryStylesFlow:
    def test_history_and_style_persist_and_reload_in_gimp_processes(self, tmp_path):
        # Arrange
        history_path = tmp_path / "prompt-history.json"
        styles_path = tmp_path / "styles"
        source_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        write_script = tmp_path / "write_settings.py"
        write_script.write_text(
            "\n".join((
                "import sys",
                f"sys.path.insert(0, {os.path.join(source_root, 'src')!r})",
                "from pathlib import Path",
                "from comfyui_plugin.storage import PromptHistory, StylePresetStore",
                f"history = PromptHistory(Path({str(history_path)!r}), limit=3)",
                "settings = {'prompt': 'portrait', 'steps': 24, 'loras': {'nested/style.safetensors': 0.7}}",
                "history.add(settings)",
                f"StylePresetStore(Path({str(styles_path)!r})).save('Portrait / Soft', settings)",
            )),
            encoding="utf-8",
        )
        read_script = tmp_path / "read_settings.py"
        read_script.write_text(
            "\n".join((
                "import sys",
                f"sys.path.insert(0, {os.path.join(source_root, 'src')!r})",
                "from pathlib import Path",
                "from comfyui_plugin.storage import PromptHistory, StylePresetStore",
                f"settings = PromptHistory(Path({str(history_path)!r})).list()[0]",
                "assert settings['prompt'] == 'portrait'",
                "assert settings['loras']['nested/style.safetensors'] == 0.7",
                f"style = StylePresetStore(Path({str(styles_path)!r})).load('Portrait-Soft')",
                "assert style == settings",
                "print('PROMPT_HISTORY_STYLES_OK')",
            )),
            encoding="utf-8",
        )
        gimp = GimpProcess(os.environ["GIMP_BIN"])

        # Act
        first_code, first_output = gimp.run_python(write_script)
        second_code, second_output = gimp.run_python(read_script)

        # Assert
        assert first_code == 0, first_output
        assert second_code == 0, second_output
        assert "PROMPT_HISTORY_STYLES_OK" in second_output
