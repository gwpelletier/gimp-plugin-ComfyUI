---
applyTo: "test/unit/**/*.py,test/support/**/*.py,test/conftest.py"
---

# Unit and test-support authoring

Read [`AGENTS.md`](../../AGENTS.md) and [`CONTRIBUTING.md`](../../CONTRIBUTING.md) before changing unit tests or test boundary adapters.

## Structure

- Use one test class per production class or function subject, for example `TestComfyUIClient` or `TestApplyParameters`.
- Name test classes `Test<ProductionSubject>` and test methods `test_<behavior>_<expected_outcome>`.
- Keep fake services, process probes, and fixture lifecycle in `test/support/`; test methods should assert production outcomes, not manage server threads.
- Keep unit tests offline, deterministic, and independent of GIMP, GTK, and external ComfyUI instances.
- Use explicit `Arrange`, `Act`, and `Assert` sections for behavior tests.

## Change expectations

- Test public behavior and boundary translation rather than private implementation details.
- Use comments only when they clarify test intent or a non-obvious fixture constraint; Arrange/Act/Assert labels are sufficient structure and do not need prose narration.
- Add failure-path coverage when changing exception handling, response parsing, or workflow validation.
- Do not turn a unit test into an integration test to avoid building a small test adapter.