import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "run_integration.py"


def load_runner_module():
    spec = importlib.util.spec_from_file_location("run_integration", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestFindGimp:
    def test_find_gimp_discovers_user_programs_gimp_three_install(self, monkeypatch, tmp_path):
        # Arrange
        module = load_runner_module()
        install = tmp_path / "Programs" / "GIMP 3" / "bin"
        executable = install / "gimp-3.exe"
        install.mkdir(parents=True)
        executable.touch()
        monkeypatch.setattr(module.platform, "system", lambda: "Windows")
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
        monkeypatch.delenv("GIMP_BIN", raising=False)
        monkeypatch.delenv("ProgramFiles", raising=False)
        monkeypatch.delenv("ProgramFiles(x86)", raising=False)

        # Act
        result = module.find_gimp()

        # Assert
        assert result == str(executable)
