import subprocess
import sys
import zipfile
from pathlib import Path

from comfyui_plugin import __version__


class TestBuildManifest:
    def test_build_contains_runtime_workflows_license_and_no_bytecode(self):
        # Arrange
        root = Path(__file__).resolve().parents[2]

        # Act
        result = subprocess.run(
            [sys.executable, "scripts/build.py"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        archives = sorted((root / "dist").glob("gimp-comfyui-*.zip"))

        # Assert
        assert result.returncode == 0, result.stderr
        assert len(archives) == 1
        assert archives[0].name == f"gimp-comfyui-{__version__}.zip"
        with zipfile.ZipFile(archives[0]) as archive:
            names = set(archive.namelist())
            assert "gimp-comfyui/gimp-comfyui.py" in names
            assert "gimp-comfyui/comfyui_plugin/client.py" in names
            assert "gimp-comfyui/workflows/sdxl-image-edit-api.json" in names
            assert "gimp-comfyui/workflows/sdxl-inpainting-api.json" in names
            assert "gimp-comfyui/workflows/sd15-image-edit-api.json" in names
            assert "gimp-comfyui/workflows/sd15-inpainting-api.json" in names
            assert "gimp-comfyui/workflows/flux-image-edit-api.json" in names
            assert "gimp-comfyui/workflows/flux-inpainting-api.json" in names
            assert "gimp-comfyui/workflows/sdxl-text-to-image-api.json" in names
            assert "gimp-comfyui/workflows/sd15-text-to-image-api.json" in names
            assert "gimp-comfyui/workflows/flux-text-to-image-api.json" in names
            assert "gimp-comfyui/workflows/krea2-turbo-text-to-image-api.json" in names
            assert "gimp-comfyui/LICENSE" in names
            assert "install.py" in names
            assert "install.sh" in names
            assert "install.ps1" in names
            assert not any(name.endswith((".pyc", ".pyo")) or "__pycache__" in name for name in names)
