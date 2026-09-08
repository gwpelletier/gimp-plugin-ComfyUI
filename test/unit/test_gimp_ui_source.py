import ast
from pathlib import Path


SOURCE_PATH = Path(__file__).resolve().parents[2] / "src" / "comfyui_plugin" / "gimp_ui.py"


class TestGimpUiSource:
    def test_vae_support_does_not_reference_undefined_family_variable(self):
        # Arrange
        tree = ast.parse(SOURCE_PATH.read_text(encoding="utf-8"))
        method = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "_update_vae_support"
        )
        assigned_names = {
            node.id
            for node in ast.walk(method)
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)
        }
        loaded_names = {
            node.id
            for node in ast.walk(method)
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
        }

        # Act
        undefined_names = loaded_names - assigned_names - {"self", "hasattr", "load_workflow", "workflow_supports_vae", "Exception", "False"}

        # Assert
        assert "selected_family" not in undefined_names


class TestGimpUiAvailabilitySource:
    """Source-level checks for the dialog's ComfyUI availability wiring."""

    @staticmethod
    def _method_calls(method_name: str) -> list[ast.Call]:
        tree = ast.parse(SOURCE_PATH.read_text(encoding="utf-8"))
        method = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == method_name
        )
        return [node for node in ast.walk(method) if isinstance(node, ast.Call)]

    @staticmethod
    def _availability_arguments(method_name: str) -> list[bool]:
        calls = TestGimpUiAvailabilitySource._method_calls(method_name)
        arguments = []
        for call in calls:
            function = call.func
            if isinstance(function, ast.Attribute) and function.attr == "_set_server_availability":
                arguments.extend(arg.value for arg in call.args if isinstance(arg, ast.Constant))
        return arguments

    def test_option_error_disables_server_dependent_controls(self):
        # Act
        arguments = self._availability_arguments("_show_option_error")

        # Assert
        assert False in arguments

    def test_apply_remote_options_enables_server_dependent_controls(self):
        # Act
        arguments = self._availability_arguments("_apply_remote_options")

        # Assert
        assert True in arguments

    def test_endpoint_row_wires_retry_button_to_connection_check(self):
        # Arrange
        source = SOURCE_PATH.read_text(encoding="utf-8")

        # Act
        calls = self._method_calls("_add_endpoint_row")

        # Assert
        assert '"view-refresh"' in source
        assert any(
            isinstance(call.func, ast.Attribute)
            and call.func.attr == "connect"
            and any(isinstance(arg, ast.Attribute) and arg.attr == "_on_retry_connection" for arg in call.args)
            for call in calls
        )

    def test_retry_handler_requests_fresh_metadata(self):
        # Act
        calls = self._method_calls("_on_retry_connection")

        # Assert
        assert any(
            isinstance(call.func, ast.Attribute) and call.func.attr == "_load_remote_options"
            for call in calls
        )

    def test_server_controls_cover_fields_but_not_endpoint_or_retry(self):
        # Arrange
        tree = ast.parse(SOURCE_PATH.read_text(encoding="utf-8"))
        build = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "_build_ui"
        )

        # Act
        server_control_names: set[str] = set()
        for node in ast.walk(build):
            if (
                isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Attribute) and target.attr == "_server_controls" for target in node.targets)
                and isinstance(node.value, ast.List)
            ):
                server_control_names = {
                    element.attr for element in node.value.elts if isinstance(element, ast.Attribute)
                }

        # Assert
        assert {"generate_button", "prompt", "mode", "workflow_selector"} <= server_control_names
        assert "endpoint" not in server_control_names
        assert "retry_button" not in server_control_names

    def test_output_mode_controls_export_directory_visibility(self):
        # Arrange
        calls = self._method_calls("_build_ui")
        handler_calls = self._method_calls("_on_output_mode_changed")

        # Act
        connected = any(
            isinstance(call.func, ast.Attribute)
            and call.func.attr == "connect"
            and any(isinstance(arg, ast.Attribute) and arg.attr == "_on_output_mode_changed" for arg in call.args)
            for call in calls
        )
        visibility_check = any(
            isinstance(call.func, ast.Attribute)
            and call.func.attr == "_set_control_visibility"
            and any(
                isinstance(arg, ast.Compare)
                and any(
                    isinstance(comparator, ast.Constant) and comparator.value == "Export directory"
                    for comparator in arg.comparators
                )
                for arg in call.args
            )
            for call in handler_calls
        )

        # Assert
        assert connected
        assert visibility_check

    def test_checkpoint_profile_change_clears_selected_loras(self):
        # Act
        calls = self._method_calls("_on_checkpoint_profile_changed")

        # Assert
        assert any(
            isinstance(call.func, ast.Attribute)
            and call.func.attr == "_clear_loras"
            for call in calls
        )
