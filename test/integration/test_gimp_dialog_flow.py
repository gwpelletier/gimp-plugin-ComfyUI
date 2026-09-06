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
                "from gi.repository import GimpUi, GLib",
                f"sys.path.insert(0, {os.path.join(source_root, 'src')!r})",
                "from comfyui_plugin.client import ComfyUIEvent, ComfyUIEventType",
                "from comfyui_plugin.gimp_ui import ComfyUIGenerationDialog",
                "GimpUi.init('gimp-comfyui-test')",
                "dialog = ComfyUIGenerationDialog(None)",
                "assert dialog.vae is not None",
                "assert dialog.mode.get_active_text() == 'Image Edit'",
                "sdxl_workflow = next(path for path in dialog.workflow_registry.list() if path['path'].endswith('sdxl-image-edit-api.json'))['path']",
                "dialog.workflow_selector.set_active_id(sdxl_workflow)",
                "assert dialog.steps.get_value_as_int() == 30",
                "dialog.mode.set_active(1)",
                "assert dialog.workflow_selector.get_active_id().endswith('sdxl-inpainting-api.json')",
                "dialog._on_generation_event(ComfyUIEvent(ComfyUIEventType.PROGRESS, value=3, maximum=10))",
                "while GLib.MainContext.default().pending(): GLib.MainContext.default().iteration(False)",
                "assert dialog.status.get_text() == 'Generating: step 3/10'",
                "dialog._on_generation_event(ComfyUIEvent(ComfyUIEventType.EXECUTING, node_id='5', node_type='KSampler'))",
                "while GLib.MainContext.default().pending(): GLib.MainContext.default().iteration(False)",
                "assert dialog.status.get_text() == 'Executing KSampler (node 5)'",
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

    def test_model_family_controls_workflows_fields_and_resource_guesses(self, tmp_path):
        # Arrange
        source_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        script_path = tmp_path / "family_dialog_harness.py"
        script_path.write_text(
            "\n".join((
                "import sys",
                "import gi",
                "gi.require_version('Gimp', '3.0')",
                "gi.require_version('GimpUi', '3.0')",
                "from gi.repository import GimpUi",
                f"sys.path.insert(0, {os.path.join(source_root, 'src')!r})",
                "from comfyui_plugin.gimp_ui import ComfyUIGenerationDialog",
                "GimpUi.init('gimp-comfyui-family-test')",
                "dialog = ComfyUIGenerationDialog(None)",
                "remote_options = {'checkpoints': ['sdxl/base.safetensors'], 'unets': ['models/flux-dev.safetensors'], 'clips': ['text_encoders/clip_l.safetensors', 'text_encoders/t5xxl.safetensors'], 'clip_t5': ['text_encoders/t5xxl.safetensors'], 'krea_diffusion_models': ['models/krea2-turbo.safetensors'], 'krea_clips': ['text_encoders/krea2.safetensors'], 'loras': [], 'vaes': ['vae/ae.safetensors'], 'samplers': ['euler'], 'schedulers': ['simple']}",
                "dialog._apply_remote_options(remote_options)",
                "dialog.checkpoint_type.set_active(1)",
                "assert dialog.workflow_selector.get_active_id().endswith('krea2-turbo-text-to-image-api.json')",
                "assert dialog.checkpoint_label.get_text() == 'Family / Diffusion Model'",
                "assert dialog.negative_prompt.get_visible() is False",
                "assert dialog.krea_clip.get_child().get_text() == 'text_encoders/krea2.safetensors'",
                "dialog.checkpoint_type.set_active(2)",
                "assert dialog.workflow_selector.get_active_id().endswith('flux-image-edit-api.json')",
                "assert dialog.clip_l.get_child().get_text() == 'text_encoders/clip_l.safetensors'",
                "assert dialog.clip_t5.get_child().get_text() == 'text_encoders/t5xxl.safetensors'",
                "assert dialog.negative_prompt.get_visible() is False",
                "dialog.checkpoint_type.set_active(3)",
                "assert dialog.checkpoint_label.get_text() == 'Family / Checkpoint'",
                "assert dialog.negative_prompt.get_visible() is True",
                "dialog.mode.set_active(1)",
                "assert dialog.workflow_selector.get_active_id().endswith('sdxl-inpainting-api.json')",
                "assert dialog.steps.get_value_as_int() == 30",
                "dialog.destroy()",
                "print('GIMP_FAMILY_DIALOG_OK')",
            )),
            encoding="utf-8",
        )
        gimp = GimpProcess(os.environ["GIMP_BIN"])

        # Act
        return_code, output = gimp.run_python(script_path)

        # Assert
        assert return_code == 0, output
        assert "GIMP_FAMILY_DIALOG_OK" in output
