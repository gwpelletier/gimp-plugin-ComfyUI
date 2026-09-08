"""Dialog availability flow against a real GIMP 3.0 process.

Requires GIMP_BIN pointing at a GIMP 3.0 executable. The harness points the
dialog at http://127.0.0.1:9 (discard port) so no ComfyUI server is needed and
the unavailable path is deterministic. The harness only writes GIMP plug-in
data files under the test GIMP profile.
"""

import os

import pytest

from test.support.gimp_process import GimpProcess


pytestmark = pytest.mark.integration


@pytest.mark.skipif(not os.environ.get("GIMP_BIN"), reason="Set GIMP_BIN to run GIMP integration tests")
class TestGimpAvailabilityFlow:
    def test_unreachable_server_disables_fields_until_retry_succeeds(self, tmp_path):
        # Arrange
        source_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        script_path = tmp_path / "availability_harness.py"
        script_path.write_text(
            "\n".join((
                "import sys",
                "import time",
                "import gi",
                "gi.require_version('Gimp', '3.0')",
                "gi.require_version('GimpUi', '3.0')",
                "from gi.repository import GimpUi, GLib",
                f"sys.path.insert(0, {os.path.join(source_root, 'src')!r})",
                "from comfyui_plugin.gimp_ui import ComfyUIGenerationDialog",
                "GimpUi.init('gimp-comfyui-availability-test')",
                "dialog = ComfyUIGenerationDialog(None)",
                "def pump_until(predicate):",
                "    deadline = time.time() + 120",
                "    while time.time() < deadline:",
                "        while GLib.MainContext.default().pending(): GLib.MainContext.default().iteration(False)",
                "        if predicate(): return True",
                "        time.sleep(0.1)",
                "    return False",
                "assert pump_until(lambda: not dialog._options_fetch_active)",
                "dialog.endpoint.set_text('http://127.0.0.1:9')",
                "dialog._on_retry_connection(dialog.retry_button)",
                "assert pump_until(lambda: not dialog._options_fetch_active)",
                "assert dialog._server_available is False",
                "assert dialog.generate_button.get_sensitive() is False",
                "assert dialog.prompt.get_sensitive() is False",
                "assert dialog.mode.get_sensitive() is False",
                "assert dialog.workflow_selector.get_sensitive() is False",
                "assert dialog.endpoint.get_sensitive() is True",
                "assert dialog.retry_button.get_sensitive() is True",
                "assert 'unavailable' in dialog.status.get_text().lower()",
                "remote_options = {'checkpoints': ['sdxl/base.safetensors'], 'unets': [], 'clips': [], 'clip_t5': [], 'krea_diffusion_models': [], 'krea_clips': [], 'loras': [], 'vaes': [], 'samplers': ['euler'], 'schedulers': ['simple']}",
                "dialog._apply_remote_options(remote_options)",
                "assert dialog._server_available is True",
                "assert dialog.generate_button.get_sensitive() is True",
                "assert dialog.prompt.get_sensitive() is True",
                "assert dialog.mode.get_sensitive() is True",
                "assert dialog.endpoint.get_sensitive() is True",
                "assert dialog.retry_button.get_sensitive() is True",
                "assert 'connected' in dialog.status.get_text().lower()",
                "dialog.destroy()",
                "print('GIMP_AVAILABILITY_OK')",
            )),
            encoding="utf-8",
        )
        gimp = GimpProcess(os.environ["GIMP_BIN"])

        # Act
        return_code, output = gimp.run_python(script_path)

        # Assert
        assert return_code == 0, output
        assert "GIMP_AVAILABILITY_OK" in output
