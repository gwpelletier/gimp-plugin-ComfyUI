# AI Eraser

The AI Eraser uses GIMP's local brush workflow and ComfyUI's inpainting workflow.

1. Open an image in GIMP.
2. Enable Quick Mask with `Shift+Q`, then paint over the object to remove with the normal GIMP brush. Paint over the background that should remain untouched.
3. Disable Quick Mask with `Shift+Q` so the painted area becomes the active selection.
4. Choose **Filters > ComfyUI > AI Eraser...**.
5. Confirm the inpainting workflow, checkpoint, and output mode, then click **Generate**.

The selection is exported as a temporary mask, sent with the image to ComfyUI, and restored results are inserted as a new layer by default. The source image and selection are not modified. This is a deferred AI operation: brush strokes remain local and only the committed erase invokes ComfyUI.

The eraser requires a workflow with a compatible mask input, such as the bundled `workflows/sdxl-inpainting-api.json`.
