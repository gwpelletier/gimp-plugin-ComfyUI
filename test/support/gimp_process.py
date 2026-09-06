import shutil
import subprocess


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