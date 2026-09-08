from pathlib import Path
from typing import Any

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

    def test_derives_data_file_paths_from_root(self, tmp_path):
        # Arrange
        paths = PluginPaths(tmp_path / "comfy")

        # Act / Assert
        assert paths.settings_file == tmp_path / "comfy" / "settings.json"
        assert paths.prompt_history == tmp_path / "comfy" / "prompt-history.json"
        assert paths.workflow_registry == tmp_path / "comfy" / "workflows" / "workflows.json"
        assert paths.styles == tmp_path / "comfy" / "styles"


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

    def test_save_raises_storage_error_and_removes_temp_file_when_replace_fails(self, tmp_path):
        # Arrange
        path = tmp_path / "settings.json"
        path.mkdir()
        store = JsonStore(path)

        # Act
        with pytest.raises(StorageError, match="Unable to write"):
            store.save({"prompt": "portrait"})

        # Assert
        assert not (tmp_path / "settings.json.tmp").exists()


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

    def test_rejects_registry_when_workflows_is_not_a_list(self, tmp_path):
        # Arrange
        path = tmp_path / "workflows.json"
        path.write_text('{"workflows": {"path": "workflow.json"}}', encoding="utf-8")

        # Act
        with pytest.raises(StorageError, match="Invalid workflow registry"):
            WorkflowRegistry(path).list()

        # Assert
        assert path.read_text(encoding="utf-8") == '{"workflows": {"path": "workflow.json"}}'

    def test_remove_returns_false_and_keeps_entries_for_unknown_path(self, tmp_path):
        # Arrange
        workflow_path = tmp_path / "workflow.json"
        workflow_path.write_text("{}", encoding="utf-8")
        registry = WorkflowRegistry(tmp_path / "workflows.json")
        registry.add([workflow_path])

        # Act
        removed = registry.remove(tmp_path / "other.json")

        # Assert
        assert not removed
        assert registry.list() == [{"path": str(workflow_path.resolve()), "title": "workflow"}]

    def test_removing_unselected_workflow_preserves_selection(self, tmp_path):
        # Arrange
        first_path = tmp_path / "first.json"
        second_path = tmp_path / "second.json"
        first_path.write_text("{}", encoding="utf-8")
        second_path.write_text("{}", encoding="utf-8")
        registry = WorkflowRegistry(tmp_path / "workflows.json")
        registry.add([first_path, second_path])
        registry.select(first_path)

        # Act
        removed = registry.remove(second_path)
        
        # Assert
        assert removed
        assert registry.selected_path == str(first_path.resolve())
        assert registry.list() == [{"path": str(first_path.resolve()), "title": "first"}]


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

    def test_rejects_non_positive_limit(self, tmp_path):
        # Arrange / Act / Assert
        with pytest.raises(ValueError, match="History limit must be positive"):
            PromptHistory(tmp_path / "history.json", limit=0)

    def test_add_rejects_non_object_entry(self, tmp_path):
        # Arrange
        history = PromptHistory(tmp_path / "history.json")
        non_object_entry: Any = ["prompt"]

        # Act
        with pytest.raises(StorageError, match="JSON objects"):
            history.add(non_object_entry)

        # Assert
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

    def test_list_returns_empty_when_styles_directory_does_not_exist(self, tmp_path):
        # Arrange
        styles = StylePresetStore(tmp_path / "styles")

        # Act
        names = styles.list()

        # Assert
        assert names == []

    def test_delete_removes_only_the_named_preset(self, tmp_path):
        # Arrange
        styles = StylePresetStore(tmp_path / "styles")
        styles.save("keep", {"steps": 10})
        styles.save("drop", {"steps": 20})

        # Act
        deleted = styles.delete("drop")

        # Assert
        assert deleted
        assert styles.list() == ["keep"]
        assert styles.load("keep") == {"steps": 10}
        assert not (tmp_path / "styles" / "drop.json").exists()

    def test_delete_raises_storage_error_when_preset_path_is_a_directory(self, tmp_path):
        # Arrange
        styles = StylePresetStore(tmp_path / "styles")
        (tmp_path / "styles" / "jammed.json").mkdir(parents=True)

        # Act
        with pytest.raises(StorageError, match="Unable to delete"):
            styles.delete("jammed")

        # Assert
        assert (tmp_path / "styles" / "jammed.json").is_dir()

    def test_load_rejects_preset_name_resolving_outside_styles_directory(self, tmp_path):
        # Arrange
        class LinkResolvingPath(type(Path())):
            """Simulate a preset file that links outside the styles directory."""

            def resolve(self, strict: bool = False) -> Path:
                resolved = super().resolve(strict=strict)
                if resolved.name == "linked.json":
                    return resolved.parent.parent / resolved.name
                return resolved

        styles = StylePresetStore(LinkResolvingPath(tmp_path / "styles"))

        # Act / Assert
        with pytest.raises(StorageError, match="outside the styles directory"):
            styles.load("linked")