import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "install.py"


def load_install_module():
    spec = importlib.util.spec_from_file_location("install_script", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestInstallPaths:
    def test_linux_path_uses_xdg_config_home(self, monkeypatch, tmp_path):
        # Arrange
        module = load_install_module()
        monkeypatch.setattr(module.platform, "system", lambda: "Linux")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        monkeypatch.setenv("GIMP_VERSION", "3.2")

        # Act
        path = module.default_plugin_dir()

        # Assert
        assert path == tmp_path / "GIMP" / "3.2" / "plug-ins"

    def test_configured_root_is_used_across_supported_platforms(self, monkeypatch, tmp_path):
        # Arrange
        module = load_install_module()
        monkeypatch.setenv("GIMP_CONFIG_DIR", str(tmp_path))
        for system in ("Linux", "Darwin", "Windows"):
            monkeypatch.setattr(module.platform, "system", lambda system=system: system)

            # Act
            path = module.default_plugin_dir()

            # Assert
            assert path == tmp_path / "plug-ins"
