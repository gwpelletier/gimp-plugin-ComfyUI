#!/usr/bin/env python3
"""Run opt-in integration tests using local GIMP and ComfyUI defaults."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

DEFAULT_COMFYUI_URL = "http://127.0.0.1:8188"


def find_gimp() -> str | None:
    """Return the configured or first available GIMP executable."""
    configured = os.environ.get("GIMP_BIN")
    if configured:
        return configured
    for candidate in ("gimp", "gimp-console"):
        executable = shutil.which(candidate)
        if executable:
            return executable
    return None


def find_comfyui_url() -> str:
    """Return the configured ComfyUI URL or the standard local endpoint."""
    return os.environ.get("COMFYUI_URL", DEFAULT_COMFYUI_URL).rstrip("/")


def comfyui_is_running(url: str) -> bool:
    """Return whether ComfyUI responds to its system endpoint."""
    try:
        with urlopen(f"{url}/system_stats", timeout=2):
            return True
    except (OSError, URLError):
        return False


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser for the integration runner."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gimp-bin", help="Override the GIMP executable")
    parser.add_argument("--comfyui-url", help="Override the ComfyUI URL")
    parser.add_argument("--no-probe", action="store_true", help="Skip the ComfyUI health probe")
    return parser


def main(arguments: list[str] | None = None) -> int:
    """Configure integration environment and run pytest."""
    parser = build_parser()
    options, pytest_arguments = parser.parse_known_args(arguments)
    gimp_bin = options.gimp_bin or find_gimp()
    comfyui_url = (options.comfyui_url or find_comfyui_url()).rstrip("/")

    if not gimp_bin:
        parser.error("GIMP was not found; set GIMP_BIN or use --gimp-bin")
    if not options.no_probe and not comfyui_is_running(comfyui_url):
        parser.error(
            f"ComfyUI did not respond at {comfyui_url}; set COMFYUI_URL or use --comfyui-url"
        )

    environment = os.environ.copy()
    environment["GIMP_BIN"] = gimp_bin
    environment["COMFYUI_URL"] = comfyui_url
    command = [sys.executable, "-m", "pytest", "-m", "integration", *pytest_arguments]
    return subprocess.run(command, cwd=Path(__file__).resolve().parents[1], env=environment).returncode


if __name__ == "__main__":
    raise SystemExit(main())
