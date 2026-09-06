---
applyTo: "src/**/*.py"
---

# Runtime source authoring

Read [`AGENTS.md`](../../AGENTS.md), [`CONTRIBUTING.md`](../../CONTRIBUTING.md), and [`docs/instruction-precedence.md`](../../docs/instruction-precedence.md) before changing runtime behavior.

## Boundary expectations

- `src/gimp_comfyui.py` is the GIMP 3 entry point. Keep registration and GIMP/GTK concerns here or in explicitly GIMP-facing modules.
- `src/comfyui_plugin/client.py` owns ComfyUI HTTP protocol behavior and must not import `gi`, GIMP, or GTK.
- `src/comfyui_plugin/workflow.py` owns workflow loading and parameter substitution. It must remain usable with a normal Python interpreter.
- Network and long-running work must be behind a worker boundary before the dockable UI is implemented; never block GIMP's main thread.

## Change expectations

- Use typed public interfaces and specific exceptions at boundaries.
- Use `PascalCase` for runtime classes and domain exceptions, `snake_case` for functions and methods, and names that make the owning boundary clear, such as `ComfyUIClient` and `WorkflowError`.
- Give public runtime APIs concise docstrings describing their contract, inputs, outputs, and raised domain errors where relevant.
- Add comments only for protocol quirks, concurrency constraints, or other non-obvious decisions; do not narrate ordinary control flow.
- Add or update unit tests for protocol/workflow behavior and integration-flow coverage for GIMP behavior.
- Keep runtime dependencies compatible with GIMP's embedded Python environment.