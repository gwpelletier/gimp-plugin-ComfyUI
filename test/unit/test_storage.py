from pathlib import Path

import pytest

from comfyui_plugin.storage import JsonStore, PluginPaths, StorageError, WorkflowRegistry


class TestPluginPaths:
    def test_ensure_creates_user_data_directories(self, tmp_path):
        # Arrange
        paths = PluginPaths(tmp_path / "comfy")

        # Act
        paths.ensure()

        # Assert
        assert paths.workflows.is_dir()
        assert paths.temporary_images.is_dir()


class TestJsonStore:
    def test_save_and_load_round_trip(self, tmp_path):
        # Arrange
        store = JsonStore(tmp_path / "settings.json")

        # Act
        store.save({"prompt": "portrait"})

        # Assert
        assert store.load() == {"prompt": "portrait"}

    def test_rejects_non_object_json(self, tmp_path):
        # Arrange
        path = tmp_path / "settings.json"
        path.write_text("[]", encoding="utf-8")

        # Act
        with pytest.raises(StorageError, match="JSON object"):
            JsonStore(path).load()

        # Assert
        assert path.exists()

    def test_rejects_malformed_json(self, tmp_path):
        # Arrange
        path = tmp_path / "settings.json"
        path.write_text("{broken", encoding="utf-8")

        # Act
        with pytest.raises(StorageError, match="Unable to read"):
            JsonStore(path).load()

        # Assert
        assert path.read_text(encoding="utf-8") == "{broken"


class TestWorkflowRegistry:
    def test_adds_json_files_once_and_removes_by_resolved_path(self, tmp_path):
        # Arrange
        workflow_path = tmp_path / "workflow.json"
        workflow_path.write_text("{}", encoding="utf-8")
        registry = WorkflowRegistry(tmp_path / "workflows.json")

        # Act
        first_count = registry.add([workflow_path, workflow_path.with_suffix(".txt")])
        second_count = registry.add([workflow_path])
        removed = registry.remove(Path(workflow_path))

        # Assert
        assert first_count == 1
        assert second_count == 0
        assert removed
        assert registry.list() == []

    def test_rejects_missing_and_non_json_files(self, tmp_path):
        # Arrange
        missing_path = tmp_path / "missing.json"
        text_path = tmp_path / "workflow.txt"
        text_path.write_text("{}", encoding="utf-8")
        registry = WorkflowRegistry(tmp_path / "workflows.json")

        # Act
        count = registry.add([missing_path, text_path])

        # Assert
        assert count == 0
        assert registry.list() == []

    def test_persists_selected_path_and_clears_it_on_removal(self, tmp_path):
        # Arrange
        workflow_path = tmp_path / "workflow.json"
        workflow_path.write_text("{}", encoding="utf-8")
        registry = WorkflowRegistry(tmp_path / "workflows.json")
        registry.add([workflow_path])

        # Act
        registry.select(workflow_path)
        selected_path = registry.selected_path
        registry.remove(workflow_path)

        # Assert
        assert selected_path == str(workflow_path.resolve())
        assert registry.selected_path is None

    def test_rejects_selecting_unregistered_path(self, tmp_path):
        # Arrange
        registry = WorkflowRegistry(tmp_path / "workflows.json")

        # Act
        with pytest.raises(StorageError, match="not registered"):
            registry.select(tmp_path / "missing.json")

        # Assert
        assert registry.selected_path is None