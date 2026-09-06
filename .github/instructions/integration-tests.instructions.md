---
applyTo: "test/integration/**/*.py"
---

# Integration-flow authoring

Read [`AGENTS.md`](../../AGENTS.md), [`CONTRIBUTING.md`](../../CONTRIBUTING.md), and [`docs/instruction-precedence.md`](../../docs/instruction-precedence.md) before changing integration tests.

## Structure

- Use one module and one test class per end-to-end flow, named with the flow suffix: `test_gimp_startup_flow.py` / `TestGimpStartupFlow`.
- Use `test_<flow>_flow.py` for modules, `Test<Flow>Flow` for classes, and `test_<behavior>_<expected_outcome>` for methods.
- Exercise real external boundaries only here: GIMP processes, ComfyUI endpoints, installed plug-ins, and real workflow execution.
- Use boundary adapters from `test/support/` for process/API invocation; keep flow tests focused on setup, action, and outcome.
- Mark the module with `pytest.mark.integration` and skip only when the required environment variable is absent.

## Change expectations

- Document required versions, environment variables, model/workflow prerequisites, and cleanup behavior.
- Keep comments focused on external-system constraints or setup decisions; do not narrate each test step.
- Verify meaningful flow outcomes, not just that a process exists.
- Keep each flow independently runnable so failures identify the broken boundary.