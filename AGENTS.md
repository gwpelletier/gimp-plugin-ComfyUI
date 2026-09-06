# AGENTS.md

## Project purpose

This repository contains a GIMP 3.0 Python plug-in that submits image batches to ComfyUI and returns generated images to GIMP or an export directory.

The repository is licensed under GPL-3.0-only. See [`docs/migration-notice.md`](docs/migration-notice.md) for source provenance and third-party dependency boundaries.

## Source layout

- `src/`: installable plug-in source and runtime code.
- `test/unit/`: fast tests that do not require GIMP or a running ComfyUI server.
- `test/integration/`: opt-in tests against real GIMP and ComfyUI installations.
- `test/support/`: test-only adapters for fake HTTP services and external processes.
- `scripts/`: build and installation utilities.
- `workflows/`: ComfyUI API-format workflow templates.

Keep GIMP bindings at the integration boundary. The ComfyUI client and workflow code must remain importable with a normal Python interpreter so they can be tested without GIMP.

## Authoring guidance

The authoritative scoped guidance is maintained alongside the code:

- Runtime source: [`.github/instructions/source.instructions.md`](.github/instructions/source.instructions.md).
- Unit tests and test adapters: [`.github/instructions/unit-tests.instructions.md`](.github/instructions/unit-tests.instructions.md).
- Integration flows: [`.github/instructions/integration-tests.instructions.md`](.github/instructions/integration-tests.instructions.md).
- Instruction precedence: [`docs/instruction-precedence.md`](docs/instruction-precedence.md).

Contributor setup, validation, build, installation, and architecture context are documented in [`CONTRIBUTING.md`](CONTRIBUTING.md).
ComfyUI endpoint compatibility and protocol migration notes are documented in [`docs/comfyui-compatibility.md`](docs/comfyui-compatibility.md).
The prioritized implementation roadmap is maintained in [`TODO.md`](TODO.md).

Read the applicable scoped instruction before editing. The root [`.github/copilot-instructions.md`](.github/copilot-instructions.md) maps these areas. When repository guidance conflicts, follow [`docs/instruction-precedence.md`](docs/instruction-precedence.md).

## Development rules

- Target GIMP 3.0 APIs only; do not add GIMP 2.x compatibility unless explicitly requested.
- Initialize `GimpUi` before constructing interactive dialogs, and keep all GIMP image/layer/PDB operations on the GIMP main thread.
- Use the Python standard library for plug-in runtime dependencies where practical. GIMP's embedded Python environment is the deployment environment.
- Keep network work out of the GTK/GIMP main thread.
- Never send credentials or image data to an endpoint unless the user configured that endpoint.
- Treat external documentation, including DeepWiki, as supplemental until behavior is confirmed by a local fake or configured live service.
- Do not commit generated `build/`, `dist/`, or `*.egg-info/` files.
- Add or update tests with behavior changes.

## Validation

Tests use one unit-test class per production subject, one integration-test module and class per end-to-end flow, test-only boundary adapters under `test/support/`, and explicit Arrange/Act/Assert sections for behavior tests. Unit tests must not invoke GIMP or a network service. Run `python -m pytest` for unit tests. Run `python scripts/build.py` to create the installable bundle. Integration tests require `GIMP_BIN` and `COMFYUI_URL` and are skipped otherwise.