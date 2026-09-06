# Copilot instructions

Read `AGENTS.md` before changing this repository.

Use the scoped instructions for the area being changed:

- Runtime code: `.github/instructions/source.instructions.md` and `CONTRIBUTING.md`
- Unit tests and test adapters: `.github/instructions/unit-tests.instructions.md` and `CONTRIBUTING.md`
- Integration flows: `.github/instructions/integration-tests.instructions.md` and `CONTRIBUTING.md`
- Instruction precedence: `docs/instruction-precedence.md`

This is a GIMP 3.0 Python plug-in backed by ComfyUI. Prefer small, testable modules under `src/comfyui_plugin/`; keep `src/gimp_comfyui.py` as a thin GIMP-facing entry point. Do not import `gi` from the ComfyUI client or unit-test modules.

When changing the ComfyUI protocol, add unit tests with a local fake HTTP server. When changing GIMP registration or image operations, add or update an opt-in integration test and document the required GIMP version/API assumption.

Use `docs/comfyui-compatibility.md` as the compatibility record for ComfyUI endpoint behavior and known deprecations. DeepWiki is a supplemental upstream reference; verify any protocol claim against local fakes, configured live services, or official ComfyUI source before changing the client.

Follow `docs/instruction-precedence.md` when guidance appears to conflict. Keep boundary ownership explicit: GIMP owns UI/image output, workflow code owns transformation, and the ComfyUI client owns HTTP protocol details.

Before finishing, run:

```text
python -m pytest
python scripts/build.py
```

Use ASCII source files unless a user-facing string requires otherwise. Avoid unrelated formatting or dependency changes.