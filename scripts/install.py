#!/usr/bin/env python3
"""Install the built plug-in into the current user's GIMP 3 plug-in directory."""

from pathlib import Path
import os
import platform
import shutil
import subprocess
import sys


def default_plugin_dir() -> Path:
    system = platform.system()
    if system == "Windows":
        app_data = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return app_data / "GIMP" / "3.0" / "plug-ins"
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "GIMP" / "3.0" / "plug-ins"
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return config_home / "GIMP" / "3.0" / "plug-ins"


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    subprocess.run([os.environ.get("PYTHON", sys.executable), str(root / "scripts" / "build.py")], check=True)
    destination = Path(os.environ.get("GIMP_PLUGIN_DIR", default_plugin_dir())) / "gimp-comfyui"
    source = root / "build" / "gimp-comfyui"
    if destination.exists():
        shutil.rmtree(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination)
    (destination / "gimp-comfyui.py").chmod(0o755)
    print(f"Installed to {destination}")


if __name__ == "__main__":
    main()