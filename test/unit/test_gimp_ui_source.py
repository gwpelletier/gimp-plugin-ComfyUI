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
