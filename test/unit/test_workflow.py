from comfyui_plugin.workflow import apply_parameters


class TestApplyParameters:
    def test_apply_parameters_replaces_markers_without_mutating_template(self):
        # Arrange
        workflow = {"1": {"inputs": {"text": "{{ prompt }}", "steps": 20}}}

        # Act
        updated = apply_parameters(workflow, {"prompt": "portrait", "steps": 30})

        # Assert
        assert updated["1"]["inputs"] == {"text": "portrait", "steps": 20}
        assert workflow["1"]["inputs"]["text"] == "{{ prompt }}"