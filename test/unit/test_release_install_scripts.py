import os
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def make_bundle(tmp_path: Path, script: Path, script_name: str) -> Path:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    shutil.copy2(script, bundle / script_name)
    source = bundle / "gimp-comfyui"
    source.mkdir()
    (source / "gimp-comfyui.py").write_text("# marker\n")
    return bundle


class TestReleaseInstallShellScript:
    @pytest.mark.skipif(shutil.which("sh") is None, reason="No POSIX shell available")
    def test_install_sh_copies_bundled_plugin_into_configured_directory(self, tmp_path):
        # Arrange
        bundle = make_bundle(tmp_path, ROOT / "scripts" / "release_install.sh", "install.sh")
        target = tmp_path / "plug-ins"
        env = dict(os.environ, GIMP_PLUGIN_DIR=str(target))

        # Act
        result = subprocess.run(["sh", "install.sh"], cwd=bundle, env=env, capture_output=True, text=True)

        # Assert
        assert result.returncode == 0, result.stderr
        assert (target / "gimp-comfyui" / "gimp-comfyui.py").exists()

    @pytest.mark.skipif(shutil.which("sh") is None, reason="No POSIX shell available")
    def test_install_sh_fails_when_bundled_plugin_folder_is_missing(self, tmp_path):
        # Arrange
        bundle = tmp_path / "bundle"
        bundle.mkdir()
        shutil.copy2(ROOT / "scripts" / "release_install.sh", bundle / "install.sh")
        env = dict(os.environ, GIMP_PLUGIN_DIR=str(tmp_path / "plug-ins"))

        # Act
        result = subprocess.run(["sh", "install.sh"], cwd=bundle, env=env, capture_output=True, text=True)

        # Assert
        assert result.returncode != 0
        assert "gimp-comfyui folder not found" in result.stderr


def _powershell_executable() -> str | None:
    return shutil.which("pwsh") or shutil.which("powershell")


class TestReleaseInstallPowerShellScript:
    @pytest.mark.skipif(_powershell_executable() is None, reason="No PowerShell executable available")
    def test_install_ps1_copies_bundled_plugin_into_configured_directory(self, tmp_path):
        # Arrange
        bundle = make_bundle(tmp_path, ROOT / "scripts" / "release_install.ps1", "install.ps1")
        target = tmp_path / "plug-ins"
        env = dict(os.environ, GIMP_PLUGIN_DIR=str(target))
        executable = _powershell_executable()

        # Act
        result = subprocess.run(
            [executable, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "install.ps1"],
            cwd=bundle,
            env=env,
            capture_output=True,
            text=True,
        )

        # Assert
        assert result.returncode == 0, result.stderr
        assert (target / "gimp-comfyui" / "gimp-comfyui.py").exists()

    @pytest.mark.skipif(_powershell_executable() is None, reason="No PowerShell executable available")
    def test_install_ps1_fails_when_bundled_plugin_folder_is_missing(self, tmp_path):
        # Arrange
        bundle = tmp_path / "bundle"
        bundle.mkdir()
        shutil.copy2(ROOT / "scripts" / "release_install.ps1", bundle / "install.ps1")
        env = dict(os.environ, GIMP_PLUGIN_DIR=str(tmp_path / "plug-ins"))
        executable = _powershell_executable()

        # Act
        result = subprocess.run(
            [executable, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "install.ps1"],
            cwd=bundle,
            env=env,
            capture_output=True,
            text=True,
        )

        # Assert
        assert result.returncode != 0
        assert "gimp-comfyui folder not found" in result.stderr
