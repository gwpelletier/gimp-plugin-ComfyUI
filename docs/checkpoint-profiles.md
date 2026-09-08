# Checkpoint Profiles

The generation dialog exposes a checkpoint profile selector beside the checkpoint name:

- `Auto` checks workflow structure first, then uses a checkpoint-name hint.
- `Flux`, `SDXL`, `SD 1.5`, and `Custom` are explicit overrides.

The dialog also exposes a top-level generation mode:

- `Image Edit` shows the SDXL, SD 1.5, and Flux image-edit workflows.
- `Inpainting` shows the SDXL, SD 1.5, and Flux inpainting workflows and requires a painted GIMP selection.

Workflow signals have higher confidence than filenames. Flux workflows are identified by nodes such as `UNETLoader` or `DualCLIPLoader`; SDXL workflows are identified by SDXL conditioning nodes. Names containing family hints such as `flux`, `sdxl`, or `sd15` are treated as medium-confidence suggestions only.

Profiles provide family-specific defaults for steps, CFG, sampler, and scheduler:

- Flux: 16 steps, CFG 1.0, Euler, Simple.
- SDXL: 30 steps, CFG 7.0, DPM++ 2M, Karras.
- SD 1.5: 20 steps, CFG 7.5, DPM++ 2M, Karras.
- Krea2-Turbo: 8 steps, CFG 1.0, Euler, Normal.

Defaults are applied only while those controls still contain their previous profile defaults, so changing a value manually preserves the user's choice. The selected profile is included in generation metadata and saved prompt/style settings.

ComfyUI's standard `/object_info` response advertises checkpoint names but does not reliably expose architecture metadata per checkpoint. The explicit override remains the authoritative escape hatch for custom or ambiguously named models.

The bundled workflow families are:

- SDXL graphs: `sdxl-image-edit-api.json` and `sdxl-inpainting-api.json`.
- SD 1.5 graphs: `sd15-image-edit-api.json` and `sd15-inpainting-api.json`.
- Flux graphs: `flux-image-edit-api.json` and `flux-inpainting-api.json`.

Krea2-Turbo is a local diffusion workflow using a diffusion model loader, a
`CLIPLoader` with `type: "krea2"`, and a VAE loader. The bundled
`krea2-turbo-text-to-image-api.json` workflow uses zeroed negative conditioning,
so the dialog hides Negative prompt for this family. The workflow is available
in Image Edit mode; an inpainting graph should be added only after the local
Krea2 model's reference-image or mask contract is verified.

Flux profiles require `UNETLoader` and `DualCLIPLoader`; SDXL profiles require
`CLIPTextEncodeSDXL`; SD 1.5 profiles require `CheckpointLoaderSimple` and
`CLIPTextEncode`. These families share the checkpoint, VAE, sampler, and
conditioning graph shape, but their text-conditioning contracts are different.
The dialog rejects a family/workflow mismatch before queueing.