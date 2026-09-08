#!/usr/bin/env python3
"""Run mutmut mutation testing inside a Docker container."""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE_PATH = REPOSITORY_ROOT / "scripts" / "mutation.Dockerfile"
IMAGE_NAME = "gimp-comfyui-mutation"


def find_docker() -> str | None:
    """Return the Docker CLI executable when available."""
    return shutil.which("docker")


def docker_daemon_is_running(docker: str) -> bool:
    """Return whether the Docker daemon answers an info probe."""
    probe = subprocess.run(
        [docker, "info", "--format", "{{.ServerVersion}}"],
        capture_output=True,
    )
    return probe.returncode == 0


def build_image(docker: str) -> int:
    """Build the mutation-testing image, reusing cached layers."""
    command = [
        docker,
        "build",
        "--tag",
        IMAGE_NAME,
        "--file",
        str(DOCKERFILE_PATH),
        str(REPOSITORY_ROOT),
    ]
    return subprocess.run(command, cwd=REPOSITORY_ROOT).returncode


def run_mutmut(docker: str, mutmut_arguments: list[str]) -> int:
    """Run mutmut with the repository mounted so results persist on the host."""
    command = [
        docker,
        "run",
        "--rm",
        "--volume",
        f"{REPOSITORY_ROOT}:/app",
        IMAGE_NAME,
        *mutmut_arguments,
    ]
    return subprocess.run(command, cwd=REPOSITORY_ROOT).returncode


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser for the mutation runner."""
    return argparse.ArgumentParser(description=__doc__)


def main(arguments: list[str] | None = None) -> int:
    """Build the mutation image and forward remaining arguments to mutmut."""
    parser = build_parser()
    _, mutmut_arguments = parser.parse_known_args(arguments)
    docker = find_docker()
    if not docker:
        parser.error("Docker was not found; install Docker Desktop or run mutmut on Linux/macOS")
    if not docker_daemon_is_running(docker):
        parser.error("The Docker daemon is not running; start Docker Desktop first")
    if build_image(docker) != 0:
        return 1
    return run_mutmut(docker, mutmut_arguments or ["run"])


if __name__ == "__main__":
    raise SystemExit(main())
