# GIMP Plugin ComfyUI Roadmap

This roadmap tracks the migration from `gimp-comfy-tools` into this GIMP 3 plug-in. Keep implementation aligned with the boundary rules in `AGENTS.md`, the scoped Copilot instructions under `.github/instructions/`, and the provenance requirements in `docs/migration-notice.md`.

## Current baseline

Completed and validated:

- [x] GPL-3.0-only relicensing and migration provenance documentation.
- [x] Standard-library ComfyUI HTTP client for health, system stats, queueing, history, upload, view, interrupt, and queue clearing.
- [x] ComfyUI node metadata discovery for checkpoints, LoRAs, VAEs, samplers, and schedulers.
- [x] API-format workflow loading, validation, marker replacement, typed generation settings, and unresolved-marker rejection.
- [x] LoRA chain injection with model and CLIP rewiring.
- [x] User-data paths, atomic JSON storage, and workflow registry persistence.
- [x] Asynchronous generation coordination outside the GIMP UI thread.
- [x] GIMP result image/layer insertion and generation metadata parasites.
- [x] Initial GIMP dialog with endpoint, workflow picker, prompts, checkpoint, generation settings, dynamic remote options, LoRA input, cancellation interrupt, and multi-output insertion.
- [x] Build/install packaging for GIMP 3.x configuration directories.
- [x] Unit, GIMP startup, ComfyUI health, and opt-in real generation integration flows.
- [x] Live validation against GIMP 3.2.4 and ComfyUI 0.34.0.

Current validation baseline: run the default suite for fast checks; the current suite collects 40 tests, with external-service flows skipped unless their prerequisites are configured. The latest local baseline is 35 passed and 5 skipped.

## Recent learnings

- DeepWiki is connected as an upstream reference, but this repository is not indexed there yet. Treat its guidance as supplemental until verified against local fakes, configured live services, or official GIMP/ComfyUI documentation.
- ComfyUI's global `/interrupt` and queue mutation endpoints are deprecated in favor of prompt-specific job APIs. Keep the current REST baseline for compatibility, and migrate only after versioned response schemas and tests exist.
- GIMP 3 interactive Python plug-ins must call `GimpUi.init()` before constructing dialogs. The normal development interpreter cannot resolve `gi`; validate GIMP-facing code with the embedded GIMP runtime.
- CI now exercises the Python 3.10 minimum and 3.12 primary development runtime. A remote Python 3.14 Actions job failed with an opaque pytest exit code despite passing locally, so 3.14 remains a local compatibility check until that runner-specific failure is reproducible.
- GitHub Actions warned that older action majors targeted deprecated Node 20 runtimes. The workflow now uses the current Node 24-compatible majors: `checkout@v7`, `setup-python@v7`, and `upload-artifact@v7`.

## Priority 1: Finish the reliable generation workflow

### 1. Selection masks

- [x] Implement `GimpImageOperations.create_mask()` using GIMP 3 selection/channel APIs.
- [x] Preserve and restore GIMP context colors and selection state.
- [x] Export masks into the per-user temporary directory with unique names.
- [x] Add a workflow transformation helper that injects `LoadImageMask` nodes into mask consumers.
- [x] Reject mask requests when the workflow has no compatible mask input.
- [x] Add unit tests for mask-node injection, missing mask inputs, and template immutability.
- [x] Add an opt-in GIMP integration flow that creates a selection, exports a mask, and verifies cleanup.
- [x] Run `workflows/inpainting-api.json` against a configured ComfyUI instance and mask-capable checkpoint before marking complete.

Implementation status: mask export, workflow injection, generation plumbing, automated tests, and live inpainting validation are complete. The interactive GIMP acceptance validation remains pending.
Staging: `test/integration/test_comfyui_inpainting_flow.py` automates the live check when `COMFYUI_MASK_WORKFLOW`, `COMFYUI_TEST_IMAGE`, `COMFYUI_TEST_MASK`, `COMFYUI_CHECKPOINT`, and `COMFYUI_URL` are provided. Operator steps are documented in [`docs/priority-1-acceptance.md`](docs/priority-1-acceptance.md).

Acceptance criteria:

- A selected region can be sent to ComfyUI without changing the user's original selection or colors.
- The generated result is inserted into GIMP and temporary mask files are cleaned up or clearly retained for diagnostics.
- Invalid mask workflows fail locally with an actionable message.

### 2. Output and cancellation robustness

- [x] Track active prompt IDs in `GenerationCoordinator`.
- [x] Make cancellation state explicit and stop polling after cancellation.
- [x] Confirm the interrupt response and distinguish cancelled jobs from failed jobs.
- [x] Clean up preview/result temporary files according to success, cancellation, and failure paths.
- [x] Add tests for cancellation before queueing, during polling, and after completion.
- [x] Add opt-in ComfyUI integration coverage that starts a longer job, cancels it, and verifies no outputs are returned.

Implementation status: cancellation state, interrupt handling, active prompt tracking, cleanup, unit coverage, and an opt-in real-ComfyUI cancellation flow are complete. The UI-level no-result-layer assertion remains covered by the coordinator guard and should be exercised during a configured GIMP acceptance run.
Staging: the manual GIMP procedure, cancellation, metadata, and cleanup checklist is documented in [`docs/priority-1-acceptance.md`](docs/priority-1-acceptance.md).

Acceptance criteria:

- Cancel never blocks the GTK thread.
- A cancelled job cannot later insert a result into GIMP.
- Completed outputs remain available when another item in a batch fails.

### 3. End-to-end result metadata

- [x] Include workflow path, prompt, negative prompt, checkpoint, LoRAs, seed, sampler, scheduler, CFG, steps, denoise, and prompt ID in layer metadata.
- [x] Add a metadata read/verification helper at the GIMP boundary.
- [x] Add an integration assertion that an inserted result layer contains the expected parasite payload.
- [x] Document the metadata key/version and compatibility behavior.

### 3a. AI eraser brush workflow

- [x] Add a dedicated AI Eraser procedure using GIMP's brush-painted Quick Mask selection.
- [x] Select the bundled inpainting workflow and provide removal prompt defaults.
- [x] Preserve the source image and selection while inserting the generated result as a layer.
- [x] Add an opt-in GIMP flow for eraser registration and painted-selection configuration.
- [x] Document the brush workflow and mask requirements.

Implementation status: **Filters > AI > ComfyUI AI Eraser...** uses local GIMP brush strokes through Quick Mask, then commits one masked inpainting request to ComfyUI. See [`docs/ai-eraser.md`](docs/ai-eraser.md).

## Priority 2: Migrate the useful source-project UI

### 4. Workflow registry UI

- [x] Replace the workflow path-only field with a selectable workflow registry view.
- [x] Support importing one or more API-format JSON workflows through a GTK file chooser.
- [x] Show workflow titles and paths, with search/filtering for larger registries.
- [x] Support removing a registry entry without deleting the underlying file.
- [x] Persist the last selected workflow through `WorkflowRegistry`.
- [x] Add unit tests for registry edge cases: duplicate paths, invalid extensions, missing files, and removal.
- [x] Add an opt-in GIMP-process flow that verifies registry selection persistence across restarts.

Implementation status: registry-backed selector, bundled workflow registration, multi-file API-format import validation, non-destructive removal, selected-path persistence, and unit coverage are complete. Full interactive GTK selection after a GIMP restart remains a manual acceptance check.

Acceptance criteria:

- Users never need to type a workflow path manually.
- UI-format workflows are rejected with a clear API-format explanation.
- Registry writes remain atomic and do not corrupt existing entries.

### 5. Dynamic model/resource controls

- [x] Replace the free-text checkpoint field with a searchable checkpoint selector.
- [x] Add a LoRA gallery/list populated from ComfyUI metadata, including strength controls.
- [x] Add optional VAE selection where the selected workflow supports it.
- [x] Preserve nested model paths exactly as returned by ComfyUI.
- [x] Keep metadata discovery asynchronous and provide local fallback values when unavailable.
- [x] Add tests for stale metadata, empty node schemas, and endpoint failure while the dialog is open.

Implementation status: searchable model selectors, metadata-backed LoRA strength rows, workflow-aware VAE selection, nested path preservation, asynchronous discovery, and local fallback behavior are complete.

### 6. Prompt history and styles

- [x] Add a persistent prompt history store with bounded retention.
- [x] Add history selection/deletion UI.
- [x] Add style preset save/load/delete support for prompts and generation settings.
- [x] Sanitize style filenames and avoid collisions.
- [x] Add unit tests for retention, malformed history files, duplicate style names, and safe filenames.
- [x] Add a GIMP integration flow for save, reload, and apply behavior.

Implementation status: bounded atomic history, selectable history application, style save/load/delete actions, safe names, and embedded-GIMP persistence coverage are complete.

### 7. Dockable panel

- [x] Decide whether the generation experience should use a true dockable `GimpUi` panel or retain a modal dialog for the first release.
- [ ] If dockable, separate persistent panel state from per-run generation state.
- [ ] Keep one generation worker per panel and disable conflicting controls while a job is active.
- [ ] Add UI-state tests where possible without importing GIMP into unit tests.
- [ ] Add a manual GIMP acceptance checklist for docking, reopening, cancellation, and restart persistence.

Decision: retain the modal dialog for the first release. The existing procedure owns one dialog per invocation, while generation work already runs behind a worker boundary; a dockable panel would add persistent lifecycle and multi-run state before the current workflow is stable enough to justify it.

## Priority 3: Progress, previews, and batch workflows

### 8. WebSocket progress and previews

- [x] Record the ComfyUI WebSocket protocol and dependency decision point in `docs/comfyui-compatibility.md`.
- [x] Evaluate a WebSocket implementation compatible with GIMP's embedded Python before adding a dependency.
- [x] Prefer a standard-library-compatible transport or explicitly package a reviewed dependency with license notices.
- [x] Add a client event model for `status`, `progress`, `executing`, `executed`, and `execution_error` messages.
- [x] Keep preview bytes and progress callbacks outside GTK until scheduled with `GLib.idle_add`.
- [x] Add fake WebSocket boundary tests or a local protocol adapter test.
- [x] Add an opt-in live flow that verifies progress events and preview cleanup.

Implementation status: standard-library WebSocket transport, typed event parsing, binary preview handling, modal progress updates, REST fallback behavior, unit coverage, and live connection coverage are complete. REST polling remains the authoritative completion path.

### 9. Batch processing

- [x] Define input sources: current image, selected open images, and folder files.
- [x] Define output modes: new GIMP images, layers in the current image, and export directory.
- [x] Add a queue model with per-item status, retry, cancel, and partial-failure reporting.
- [x] Prevent concurrent jobs from sharing mutable workflow state.
- [x] Add unit tests for queue transitions and partial failures.
- [x] Add an integration flow for at least two inputs and two outputs.
- [x] Document resource usage and whether jobs are sequential by default.

Implementation status: `BatchQueue` and `GenerationCoordinator.run_batch()` process one request at a time, deep-copy workflow inputs, preserve partial successes, support retries/cancellation, and expose per-item updates. The modal dialog currently supports one staged image per invocation; folder/open-image selection remains an API boundary for the next UI surface.

### 10. Export and file lifecycle

- [x] Add an output directory selector and safe filename generation.
- [x] Preserve source extensions where possible and validate downloaded content before export.
- [x] Avoid overwriting user files unless explicitly requested.
- [x] Add tests for filename collisions, invalid paths, and failed writes.
- [x] Add an integration assertion that exported files can be reopened by GIMP.

Implementation status: the dialog offers layer, new-image, and export-directory output modes. `ImageExporter` validates PNG/JPEG/GIF/WebP signatures, preserves extensions, creates collision-safe names, and requires explicit overwrite.

## Priority 4: Quality and release hardening

### 11. GIMP API coverage

- [x] Add an opt-in flow that invokes the registered procedure with a real image.
- [x] Initialize `GimpUi` before constructing the interactive dialog.
- [x] Verify interactive-mode behavior, dialog opening, result insertion, and parasite metadata.
- [x] Test on the supported GIMP 3 minor versions used by release builds.
- [x] Keep `gi` imports at the GIMP boundary and document expected editor diagnostics.

Implementation status: the opt-in GIMP process flows cover registration, real-image procedure invocation, startup, insertion, metadata, export reopen, and persistence. The current release validation target is GIMP 3.2.4; interactive manual steps are recorded in [`docs/priority-4-acceptance.md`](docs/priority-4-acceptance.md).

### 12. ComfyUI compatibility

- [x] Test against the supported ComfyUI API endpoints and record the minimum known version.
- [x] Add workflow compatibility checks for missing nodes and unsupported inputs.
- [x] Verify checkpoint, sampler, scheduler, LoRA, VAE, and mask names against `/object_info`.
- [x] Add clear errors for custom-node workflows whose nodes are unavailable.
- [x] Keep the live generation integration test opt-in to avoid accidental GPU use in CI.

Implementation status: ComfyUI 0.34.0 is the validated baseline. `/object_info` compatibility validation rejects unavailable nodes, inputs, and resource values while preserving the known legacy image-upload hint.

### 13. Packaging and licensing

- [x] Add a release manifest test for executable layout, workflow files, `LICENSE`, and no bytecode.
- [x] Keep the package version single-sourced.
- [x] Review any future dependency against GPL compatibility and include its license notices.
- [x] Confirm GIMP 3.x per-user installation paths on Linux, macOS, Windows, Flatpak, and AppImage.
- [x] Add a release checklist to `CONTRIBUTING.md`.
- [x] Do not include development virtual environments, generated builds, or vendored unrelated packages.

Implementation status: manifest and version tests pass, runtime dependencies remain standard-library-only, installation paths are covered for the supported platform branches, and the build excludes bytecode and development artifacts.

## Suggested implementation order

1. Run configured live inpainting and GIMP acceptance flows for Priority 1.
2. Complete the workflow registry UI.
3. Replace free-text model settings with dynamic selectors.
4. Add prompt history and styles.
5. Decide and implement the dockable panel.
6. Migrate cancellation to the supported ComfyUI job API when version coverage is confirmed.
7. Add WebSocket progress/previews only after dependency compatibility is resolved.
8. Implement batch processing and export modes.
9. Expand release and cross-platform packaging validation.

## Definition of done for each item

A migration item is complete only when:

- Runtime ownership is in the correct `src/` boundary.
- Public APIs have IDE-visible docstrings and typed parameters where practical.
- Happy-path and meaningful sad-path unit tests exist.
- External behavior has an opt-in integration-flow test when applicable.
- A real GIMP or ComfyUI end-to-end check has been run for user-facing behavior.
- Documentation, packaging, and license provenance are updated.
- `python -m pytest`, `python scripts/build.py`, and `git diff --check` pass.
