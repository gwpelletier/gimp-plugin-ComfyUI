# Contributing

## Start here

Read [`AGENTS.md`](AGENTS.md) first. It defines the repository-wide contract and links to the applicable scoped Copilot instructions. Use [`docs/instruction-precedence.md`](docs/instruction-precedence.md) when guidance appears to conflict.

The `.github/instructions/` files are the authoritative authoring rules for matching paths:

- Runtime Python: [source instructions](.github/instructions/source.instructions.md)
- Unit tests and test adapters: [unit-test instructions](.github/instructions/unit-tests.instructions.md)
- Integration flows: [integration-test instructions](.github/instructions/integration-tests.instructions.md)
- Shared Python rules: [Python instructions](.github/instructions/python.instructions.md)

The root [`README.md`](README.md) provides project orientation and usage. It does not override those instructions.

## Runtime architecture

- `src/gimp_comfyui.py` owns GIMP 3 procedure registration and the GIMP-facing application boundary.
- `src/comfyui_plugin/client.py` owns ComfyUI HTTP requests and returns Python values or domain exceptions.
- `src/comfyui_plugin/workflow.py` owns workflow loading and parameter substitution.

GIMP code owns image/layer creation, progress, cancellation, and export. Workflow code must remain independent of GIMP and network APIs. The ComfyUI client must not import `gi`, GIMP, or GTK.

## Test architecture

- `test/unit/` tests one production subject at a time with local fakes.
- `test/support/` owns fake service and process boundary adapters.
- `test/integration/` tests one real GIMP or ComfyUI flow per module and class.

Unit tests are offline and deterministic. Integration tests use real external services only when their prerequisites are configured.

## Development setup

Use Python **3.12** for development and CI. Python 3.10 is the supported minimum; Python 3.13 may be used for an additional compatibility check. The Python process that runs the plug-in is the one provided by the GIMP 3 installation, so verify that runtime separately from the development virtual environment.

```sh
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test]'
```

Runtime dependencies are intentionally empty. GIMP supplies the `gi` bindings in its embedded Python environment.

## Validation

Run the default suite and build before submitting a change:

```sh
python -m pytest
python scripts/build.py
```

Unit tests use local fakes and do not require GIMP, GTK, a GPU, model files, or a network service. Integration tests are opt-in:

```sh
GIMP_BIN=/path/to/gimp \
COMFYUI_URL=http://127.0.0.1:8188 \
python -m pytest -m integration
```

Integration prerequisites are skipped with an actionable message when their environment variables are absent.

## Build and install

`python scripts/build.py` creates a versioned `dist/gimp-comfyui-<version>.zip` archive and removes stale archives from earlier builds. To install into the current user's standard GIMP 3 plug-in directory:

```sh
python scripts/install.py
```

Set `GIMP_PLUGIN_DIR` to use a different destination. Close and restart GIMP after installation.

The bundle follows GIMP 3's Python plug-in layout: the executable `gimp-comfyui.py` is inside the same-named `gimp-comfyui/` directory. The build includes only the executable, importable runtime package, workflow templates, and `LICENSE`; generated build directories and Python bytecode are excluded.

The implementation follows the [GIMP 3 Python plug-in tutorial](https://developer.gimp.org/resource/writing-a-plug-in/tutorial-python/), [GIMP 3 API reference](https://developer.gimp.org/api/3.0/), and [GIMP plug-in distribution guidance](https://developer.gimp.org/resource/distributing-plug-ins/). ComfyUI integration follows DeepWiki's [API and programmatic usage](https://deepwiki.com/Comfy-Org/ComfyUI/7-api-and-programmatic-usage), [REST API reference](https://deepwiki.com/Comfy-Org/ComfyUI/7.1-rest-api-reference), and [workflow JSON format](https://deepwiki.com/Comfy-Org/ComfyUI/7.3-workflow-json-format). The repository itself is not yet indexed on DeepWiki.

## Change expectations

Keep GIMP bindings at the application boundary, ComfyUI HTTP behavior in the client, and workflow transformation in workflow modules. Add unit coverage for local behavior and integration-flow coverage when a change crosses a real GIMP or ComfyUI boundary.