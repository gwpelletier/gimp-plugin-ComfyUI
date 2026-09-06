# GIMP Plugin ComfyUI

A GIMP 3.0 Python plug-in foundation for batch AI image editing through ComfyUI.

Licensed under GPL-3.0-only. See [`docs/migration-notice.md`](docs/migration-notice.md) for migration provenance and dependency licensing boundaries.

## Current status

The repository contains the installable plug-in boundary, ComfyUI queue/history client, workflow substitution, selection masks, cancellation handling, generation metadata, build/install scripts, and unit/integration test coverage. Workflow registry UI and dynamic resource controls are the next implementation slice.

## Layout

- `src/` - plug-in and runtime source.
- `test/` - unit tests and opt-in integration tests.
- `workflows/` - ComfyUI API-format templates.
- `TODO.md` - prioritized migration roadmap and completion criteria.
- `scripts/build.py` - creates a versioned installable plug-in archive in `dist/`.
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

Close GIMP, then run:

```sh
python3 scripts/install.py
```

The installer uses the standard per-user plug-in directory for the configured GIMP version (GIMP 3.2 by default):

- Linux: `~/.config/GIMP/<version>/plug-ins/`
- macOS: `~/Library/Application Support/GIMP/<version>/plug-ins/`
- Windows: `%APPDATA%/GIMP/<version>/plug-ins/`

Set `GIMP_PLUGIN_DIR` to override the destination, or set `GIMP_CONFIG_DIR` and `GIMP_VERSION` for automatic path construction. Restart GIMP after installation. The plug-in is currently registered under `Filters > AI > ComfyUI Batch...`.
