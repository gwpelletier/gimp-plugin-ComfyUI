# Workflow Filtering and Field Policy

This document defines the product contract for workflow mode filtering, model-family selection, and the fields shown in the generation dialog. It exists to keep UI behavior, workflow metadata, and preflight validation aligned as more ComfyUI workflows are added.

## Goals

The filtering system should:

- help users choose a workflow by intent rather than by filename;
- prevent a model-family choice from silently selecting incompatible resources;
- make Auto convenient without hiding disagreement between user input and workflow structure;
- show family-specific controls consistently;
- reject invalid combinations before a request reaches ComfyUI;
- preserve support for imported workflows without requiring every workflow to use the bundled node layout.

## Decisions

### Mode classification

The open product question is whether to add a separate `Text to Image` mode or let workflow capability determine every mode. The recommended direction is:

1. Use **registry metadata** as the primary user-facing classification. Each registered workflow should declare one mode: `Text to Image`, `Image Edit`, or `Inpainting`.
2. Use **workflow content as validation**, not as the only presentation rule. The loader should verify that metadata is plausible, for example that an Inpainting workflow has a mask input and that Image Edit has an image input.
3. Treat **filename conventions as non-authoritative**. Names such as `*-inpainting-api.json` may remain useful defaults when importing legacy entries, but renaming a file must not change its behavior.

This gives users stable intent-based filtering while retaining enough structural checking to catch stale or misleading registry entries. It also avoids treating every workflow that happens to contain a `LoadImage` node as the same product experience.

The separate `Text to Image` mode should be introduced if the UI needs to distinguish workflows that do not consume a source image from Image Edit workflows that do. Until that decision is implemented, registry metadata should still support all three values so the data model does not conflate them.

### Auto family selection

Auto uses **both** available signals:

- the selected workflow's node structure;
- the model name entered or selected by the user.

The workflow is the stronger signal for determining which fields and parameters are required. The entered model name is an independent compatibility signal. When both signals are reliable and disagree, the dialog should show a clear conflict and prevent generation until the user changes the family, workflow, or model.

When only one signal is available, Auto may use it. When neither signal is reliable, the workflow remains selectable but the UI should avoid pretending that a family-specific resource contract has been established.

### Family selection and model resources

Explicit family selection should be more than a workflow filter if the ComfyUI metadata makes that possible. The unresolved problem is that the current family selector can narrow workflows while still allowing a user to choose an unrelated checkpoint, diffusion model, or encoder from the server's global option list.

The implementation should investigate these progressively stronger guarantees:

- resource metadata supplied by ComfyUI or a known node schema;
- family-specific resource lists derived from the selected workflow;
- conservative name-based hints as a fallback, clearly treated as heuristics;
- final workflow/resource validation before queueing.

The desired result is an actionable mismatch before generation, not a confusing ComfyUI execution failure. If a reliable guarantee cannot be made for arbitrary custom resources, the UI must state that the family filter is advisory and retain the final preflight check.

### Krea2-Turbo and Inpainting

Krea2-Turbo is currently excluded from Inpainting because no bundled Krea workflow supports a mask input. This is a current capability decision, not a claim that Krea can never support inpainting. A future mask-capable Krea workflow should trigger a deliberate review of the restriction and its tests.

### Field authority

Family selection is the authority for family-specific resource fields and prompt-field visibility. This keeps the UI contract stable across workflows in the same family. The selected workflow remains the final authority for whether the request can actually be executed, and preflight validation must reject missing or incompatible inputs.

This distinction is intentional:

- family selection answers "what controls should the user work with?";
- workflow validation answers "can this exact workflow accept the resulting request?"

### Unknown workflows

Unknown or custom workflows remain **Auto-only**. `Custom` may remain an internal inference result for defaults and diagnostics, but it should not be exposed as a user-selectable family until there is a defined resource and field contract for it.

## Required behavior

The implementation phase is complete when:

- registry entries have explicit mode metadata;
- imported workflows receive metadata without relying on future filename changes;
- invalid mode metadata produces an actionable warning or prevents selection;
- Auto detects and reports reliable workflow/model-family conflicts;
- explicit family selection filters workflows and investigates resource compatibility;
- Krea remains unavailable for Inpainting unless a supported mask-capable workflow is deliberately added;
- family-specific field visibility is stable and covered by tests;
- unknown workflows remain available through Auto without being mislabeled as a known family;
- unit and opt-in GIMP integration tests cover these contracts.

## Non-goals

- inferring every arbitrary custom-node workflow perfectly;
- making filename parsing a permanent compatibility contract;
- exposing a Custom family before its resource semantics are defined;
- allowing a server-side execution error to serve as the primary compatibility check.