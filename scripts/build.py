#!/usr/bin/env python3
"""Build an installable plug-in directory and zip archive."""

from pathlib import Path
import shutil
import sys
import zipfile


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build" / "gimp-comfyui"
DIST = ROOT / "dist"


def project_version() -> str:
    sys.path.insert(0, str(ROOT / "src"))
    from comfyui_plugin import __version__

    return __version__


def main() -> None:
    version = project_version()
    if BUILD.exists():
        shutil.rmtree(BUILD)
    BUILD.mkdir(parents=True)
    shutil.copy2(ROOT / "src" / "gimp_comfyui.py", BUILD / "gimp-comfyui.py")
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc")
    shutil.copytree(ROOT / "src" / "comfyui_plugin", BUILD / "comfyui_plugin", ignore=ignore)
    shutil.copytree(ROOT / "workflows", BUILD / "workflows", ignore=ignore)
    shutil.copy2(ROOT / "LICENSE", BUILD / "LICENSE")
    (BUILD / "gimp-comfyui.py").chmod(0o755)
    DIST.mkdir(exist_ok=True)
    for previous_archive in DIST.glob("gimp-comfyui-*.zip"):
        previous_archive.unlink()
    archive = DIST / f"gimp-comfyui-{version}.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as output:
        for path in BUILD.rglob("*"):
            if path.is_file():
                output.write(path, Path("gimp-comfyui") / path.relative_to(BUILD))
    print(f"Built {archive}")


if __name__ == "__main__":
    main()