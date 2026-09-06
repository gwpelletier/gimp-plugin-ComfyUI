# Priority 1 Acceptance

The automated unit suite and local GIMP boundary flow are complete. These live checks require the operator's configured GIMP and ComfyUI installations, model files, and image assets, so they remain opt-in.

## ComfyUI inpainting

Prepare an API-format workflow exported from the ComfyUI UI that:

- Loads the source image through a `LoadImage` node.
- Has at least one node input named `mask`, such as `VAEEncodeForInpaint` or `SetLatentNoiseMask`.
- Produces a `SaveImage` output.
- Uses node classes and resource names available on the target ComfyUI instance.

Run:

```sh
COMFYUI_URL=http://127.0.0.1:8188 \
COMFYUI_MASK_WORKFLOW=/path/to/inpainting-api-workflow.json \
COMFYUI_TEST_IMAGE=/path/to/source.png \
COMFYUI_TEST_MASK=/path/to/mask.png \
COMFYUI_CHECKPOINT=path/to/checkpoint.safetensors \
python -m pytest test/integration/test_comfyui_inpainting_flow.py
```

The test uploads both files, injects `LoadImageMask` into the workflow's mask consumers, queues the graph, downloads the first output, and verifies the PNG signature. A successful run closes the remaining live ComfyUI gate in Priority 1 section 1.

## GIMP procedure and cancellation acceptance

Install the current bundle with `python scripts/install.py`, restart GIMP, and configure a reachable ComfyUI endpoint.

1. Open a test image and create a visible selection.
2. Run `Filters > AI > ComfyUI Batch...`.
3. Select a mask-capable API workflow, enter a valid checkpoint and prompt, and generate.
4. Verify the result layer is inserted, the original selection remains unchanged, and the temporary source/mask files are removed after the worker finishes.
5. Inspect the result layer's `comfy-data-v1` parasite and verify the workflow path, prompts, checkpoint, LoRAs, seed, sampler, scheduler, CFG, steps, denoise, and prompt ID.
6. Repeat with a deliberately long-running workflow, press Cancel, and verify no result layer appears after the worker stops.

Record the GIMP version, ComfyUI version, workflow path, checkpoint name, and outcome in the release or test notes. Do not enable these checks in CI unless the required services and model assets are explicitly provisioned.