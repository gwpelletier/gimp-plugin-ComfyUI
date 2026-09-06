# GIMP Plugin ComfyUI

A GIMP 3.0 Python plug-in foundation for batch AI image editing through ComfyUI.

## Current status

The repository contains the installable plug-in boundary, ComfyUI queue/history client, workflow substitution, build/install scripts, and unit/integration test scaffolding. The dockable batch panel and image conversion pipeline are the next implementation slice.

## Layout

- `src/` - plug-in and runtime source.
- `test/` - unit tests and opt-in integration tests.
- `workflows/` - ComfyUI API-format templates.
- `scripts/build.py` - creates a versioned installable plug-in archive in `dist/`.
- `scripts/install.py` - builds and installs for the current user.
- `CONTRIBUTING.md` - contributor workflow, validation, and build/install process.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for development, testing, build, installation, and authoring guidance. Use [`docs/instruction-precedence.md`](docs/instruction-precedence.md) when repository rules appear to conflict.

## Quick start

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test]'
python -m pytest
python scripts/build.py
```

## Install in GIMP 3

Close GIMP, then run:

```sh
python3 scripts/install.py
```

The installer uses the standard per-user plug-in directory:

- Linux: `~/.config/GIMP/3.0/plug-ins/`
- macOS: `~/Library/Application Support/GIMP/3.0/plug-ins/`
- Windows: `%APPDATA%/GIMP/3.0/plug-ins/`

Set `GIMP_PLUGIN_DIR` to override the destination. Restart GIMP after installation. The plug-in is currently registered under `Filters > AI > ComfyUI Batch...`.
