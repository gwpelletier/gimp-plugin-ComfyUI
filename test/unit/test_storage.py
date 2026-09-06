from pathlib import Path

import pytest

from comfyui_plugin.storage import (
    JsonStore,
    PluginPaths,
    PromptHistory,
    StorageError,
    StylePresetStore,
    WorkflowRegistry,
)


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


class TestPromptHistory:
    def test_adds_new_entries_first_and_retains_only_the_limit(self, tmp_path):
        # Arrange
        history = PromptHistory(tmp_path / "history.json", limit=2)

        # Act
        history.add({"prompt": "first"})
        history.add({"prompt": "second"})
        history.add({"prompt": "third"})

        # Assert
        assert history.list() == [{"prompt": "third"}, {"prompt": "second"}]

    def test_rejects_malformed_entries(self, tmp_path):
        # Arrange
        path = tmp_path / "history.json"
        path.write_text('{"entries": ["not an object"]}', encoding="utf-8")

        # Act
        with pytest.raises(StorageError, match="prompt history"):
            PromptHistory(path).list()

        # Assert
        assert path.exists()

    def test_deletes_valid_entry_and_ignores_unknown_index(self, tmp_path):
        # Arrange
        history = PromptHistory(tmp_path / "history.json")
        history.add({"prompt": "keep"})

        # Act
        deleted = history.delete(0)
        missing = history.delete(0)

        # Assert
        assert deleted
        assert not missing
        assert history.list() == []


class TestStylePresetStore:
    def test_sanitizes_names_and_round_trips_settings(self, tmp_path):
        # Arrange
        styles = StylePresetStore(tmp_path / "styles")

        # Act
        name = styles.save("  portrait / soft light  ", {"prompt": "portrait"})

        # Assert
        assert name == "portrait-soft-light"
        assert styles.list() == [name]
        assert styles.load(name) == {"prompt": "portrait"}

    def test_overwrites_same_sanitized_name_without_collision(self, tmp_path):
        # Arrange
        styles = StylePresetStore(tmp_path / "styles")
        styles.save("cinematic", {"steps": 10})

        # Act
        styles.save("cinematic", {"steps": 20})

        # Assert
        assert styles.list() == ["cinematic"]
        assert styles.load("cinematic")["steps"] == 20

    def test_rejects_empty_safe_name_and_handles_missing_delete(self, tmp_path):
        # Arrange
        styles = StylePresetStore(tmp_path / "styles")

        # Act
        with pytest.raises(StorageError, match="safe filename"):
            styles.save("...", {})
        deleted = styles.delete("missing")

        # Assert
        assert not deleted

    def test_rejects_selecting_unregistered_path(self, tmp_path):
        # Arrange
        registry = WorkflowRegistry(tmp_path / "workflows.json")

        # Act
        with pytest.raises(StorageError, match="not registered"):
            registry.select(tmp_path / "missing.json")

        # Assert
        assert registry.selected_path is None