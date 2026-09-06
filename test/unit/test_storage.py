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