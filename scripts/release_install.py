#!/usr/bin/env python3
"""Install a pre-built plug-in release into the current user's GIMP 3 plug-in directory.

This script is bundled into the release archive next to the ``gimp-comfyui``
folder, so it works without cloning the repository or having ``src``/``scripts``
available.
"""

from pathlib import Path
import os
import platform
import shutil


def default_plugin_dir() -> Path:
    config_version = os.environ.get("GIMP_VERSION", "3.2")
    configured_root = os.environ.get("GIMP_CONFIG_DIR")
    system = platform.system()
    if system == "Windows":
        app_data = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        root = Path(configured_root) if configured_root else app_data / "GIMP" / config_version
        return root / "plug-ins"
    if system == "Darwin":
        root = Path(configured_root) if configured_root else Path.home() / "Library" / "Application Support" / "GIMP" / config_version
        return root / "plug-ins"
    if configured_root:
        return Path(configured_root) / "plug-ins"
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return config_home / "GIMP" / config_version / "plug-ins"


def main() -> None:
    source = Path(__file__).resolve().parent / "gimp-comfyui"
    if not source.is_dir():
        raise SystemExit("gimp-comfyui folder not found next to this script")
    destination = Path(os.environ.get("GIMP_PLUGIN_DIR", default_plugin_dir())) / "gimp-comfyui"
    if destination.exists():
        shutil.rmtree(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination)
    (destination / "gimp-comfyui.py").chmod(0o755)
    print(f"Installed to {destination}")


if __name__ == "__main__":
    main()
