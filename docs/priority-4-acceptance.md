# Priority 4 Acceptance

## Validated environment

- GIMP 3.2.4 on Linux, installed from the current build with `python scripts/install.py`.
- ComfyUI 0.34.0 on `http://127.0.0.1:8188`.
- Python 3.10 and 3.12 remain the CI support matrix.

## Automated checks

Run the default suite and build:

```sh
python -m pytest
python scripts/build.py
python scripts/run_integration.py
```

The integration runner discovers `GIMP_BIN` and `COMFYUI_URL`. GPU-dependent generation, inpainting, and cancellation flows additionally require their documented workflow, image, and checkpoint variables.

The live Priority 4 checks cover:

- ComfyUI version/system stats and `/object_info` validation for the bundled API workflow.
- Registered `python-fu-comfyui-generate` procedure lookup with a real GIMP image at the noninteractive boundary.
- GIMP image/layer insertion, metadata, export reopen, startup, and workflow persistence.

## Manual interactive check

With GIMP restarted after installation:

1. Open an image and invoke **Filters > ComfyUI > Batch**.
2. Confirm the dialog opens after `GimpUi.init()`, then cancel it and confirm no result layer is created.
3. Configure a live workflow, generate one result, and verify the result layer and `comfy-data-v1` metadata parasite.
4. Select **Export directory**, generate again, and verify the exported file opens in GIMP.
5. Restart GIMP and confirm workflow registry selection, prompt history, and styles persist.

Record the GIMP version, ComfyUI version, workflow, checkpoint, and outcome with release validation.
