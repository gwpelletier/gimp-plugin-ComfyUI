# Checkpoint Profiles

The generation dialog exposes a checkpoint profile selector beside the checkpoint name:

- `Auto` checks workflow structure first, then uses a checkpoint-name hint.
- `Flux`, `SDXL`, `SD 1.5`, and `Custom` are explicit overrides.

Workflow signals have higher confidence than filenames. Flux workflows are identified by nodes such as `UNETLoader` or `DualCLIPLoader`; SDXL workflows are identified by SDXL conditioning nodes. Names containing family hints such as `flux`, `sdxl`, or `sd15` are treated as medium-confidence suggestions only.

Profiles provide conservative defaults for steps, CFG, sampler, and scheduler. Defaults are applied only while those controls still contain their previous profile defaults, so changing a value manually preserves the user's choice. The selected profile is included in generation metadata and saved prompt/style settings.

ComfyUI's standard `/object_info` response advertises checkpoint names but does not reliably expose architecture metadata per checkpoint. The explicit override remains the authoritative escape hatch for custom or ambiguously named models.