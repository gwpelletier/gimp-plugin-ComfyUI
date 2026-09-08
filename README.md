# GIMP Plugin ComfyUI

A GIMP 3.0 Python plug-in foundation for batch AI image editing through ComfyUI.

Licensed under GPL-3.0-only. See [`docs/migration-notice.md`](docs/migration-notice.md) for migration provenance and dependency licensing boundaries.

## Current status

The repository contains the installable plug-in boundary, ComfyUI queue/history client, workflow substitution, selection masks, cancellation handling, generation metadata, workflow registry UI, build/install scripts, and unit/integration test coverage. Dynamic model/resource controls are the next implementation slice.

## Layout

- `src/` - plug-in and runtime source.
- `test/` - unit tests and opt-in integration tests.
- `workflows/` - ComfyUI API-format templates.
- `TODO.md` - prioritized migration roadmap and completion criteria.
- `scripts/build.py` - creates a versioned installable plug-in archive in `dist/`, bundled with a standalone `install.py`.

For brush-assisted object removal, see [`docs/ai-eraser.md`](docs/ai-eraser.md). The **ComfyUI AI Eraser** procedure uses GIMP Quick Mask and the bundled inpainting workflow.
- `scripts/install.py` - builds and installs for the current user.
- `CONTRIBUTING.md` - contributor workflow, validation, and build/install process.
- `docs/comfyui-compatibility.md` - supported ComfyUI baseline, endpoint notes, and protocol migration plan.

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

### From a release archive (no clone required)

Download `gimp-comfyui-<version>.zip` from the [releases page](../../releases), extract it, close GIMP, then run the installer that matches your platform from inside the extracted folder:

- Windows (no Python required): `powershell -ExecutionPolicy Bypass -File install.ps1`
- Linux/macOS (no Python required): `sh install.sh`
- Any platform with Python 3 installed: `python3 install.py`


### From a repository clone

Close GIMP, then run:

```sh
python3 scripts/install.py
```

All installers use the standard per-user plug-in directory for the configured GIMP version (GIMP 3.2 by default):

- Linux: `~/.config/GIMP/<version>/plug-ins/`
- macOS: `~/Library/Application Support/GIMP/<version>/plug-ins/`
- Windows: `%APPDATA%/GIMP/<version>/plug-ins/`

Set `GIMP_PLUGIN_DIR` to override the destination, or set `GIMP_CONFIG_DIR` and `GIMP_VERSION` for automatic path construction. Restart GIMP after installation.

Use `Filters > ComfyUI > Generate...` with an image, or `Tools > ComfyUI > Generate Image...` without one.
