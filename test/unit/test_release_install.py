import importlib.util
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "release_install.py"


def load_release_install_module():
    spec = importlib.util.spec_from_file_location("release_install_script", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestReleaseInstallPaths:
    def test_linux_path_uses_xdg_config_home(self, monkeypatch, tmp_path):
        # Arrange
        module = load_release_install_module()
        monkeypatch.setattr(module.platform, "system", lambda: "Linux")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        monkeypatch.setenv("GIMP_VERSION", "3.2")

        # Act
        path = module.default_plugin_dir()

        # Assert
        assert path == tmp_path / "GIMP" / "3.2" / "plug-ins"

    def test_configured_root_is_used_across_supported_platforms(self, monkeypatch, tmp_path):
        # Arrange
        module = load_release_install_module()
        monkeypatch.setenv("GIMP_CONFIG_DIR", str(tmp_path))
        for system in ("Linux", "Darwin", "Windows"):
            monkeypatch.setattr(module.platform, "system", lambda system=system: system)

            # Act
            path = module.default_plugin_dir()

            # Assert
            assert path == tmp_path / "plug-ins"


class TestReleaseInstallMain:
    def test_main_copies_bundled_plugin_next_to_script_into_target_directory(self, monkeypatch, tmp_path):
        # Arrange
        module = load_release_install_module()
        source = Path(module.__file__).resolve().parent / "gimp-comfyui"
        target = tmp_path / "plug-ins"
        monkeypatch.setenv("GIMP_PLUGIN_DIR", str(target))
        created_source = not source.exists()
        if created_source:
            source.mkdir()
            (source / "gimp-comfyui.py").write_text("# marker\n")

        try:
            # Act
            module.main()

            # Assert
            assert (target / "gimp-comfyui" / "gimp-comfyui.py").exists()
        finally:
            if created_source:
                import shutil

                shutil.rmtree(source)

    def test_main_raises_when_bundled_plugin_folder_is_missing(self, monkeypatch, tmp_path):
        # Arrange
        module = load_release_install_module()
        source = Path(module.__file__).resolve().parent / "gimp-comfyui"
        monkeypatch.setenv("GIMP_PLUGIN_DIR", str(tmp_path))
        assert not source.exists()

        # Act / Assert
        with pytest.raises(SystemExit, match="gimp-comfyui folder not found"):
            module.main()
