import shutil
import subprocess
from pathlib import Path


class GimpProcess:
    """Boundary adapter for invoking a real GIMP executable in integration tests."""

    def __init__(self, executable: str):
        self.executable = shutil.which(executable) or executable

    def version_return_code(self) -> tuple[int, str]:
        result = subprocess.run(
            [self.executable, "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode, result.stderr

    def run_python(self, script_path: Path) -> tuple[int, str]:
        """Run a Python evaluator harness through GIMP and return its output."""
        command = f'exec(open({str(script_path)!r}, encoding="utf-8").read())'
        result = subprocess.run(
            [
                self.executable,
                "--no-interface",
                "--no-data",
                "--no-fonts",
                "--console-messages",
                "--batch-interpreter=python-fu-eval",
                f"--batch={command}",
                "--quit",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode, result.stdout + result.stderr