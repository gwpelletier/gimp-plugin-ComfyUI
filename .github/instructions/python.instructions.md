---
applyTo: "src/**/*.py,test/**/*.py,scripts/**/*.py"
---

# Python conventions

- Use type annotations for public functions and dataclasses for structured values.
- Follow PEP 8 naming: `PascalCase` for classes and exceptions, `snake_case` for functions, methods, variables, and modules, and `UPPER_SNAKE_CASE` for module constants.
- Use descriptive names; do not use one-letter names except for conventional short-lived indices or comprehensions.
- Prefix internal implementation details with a single underscore. Do not use double underscores for ordinary encapsulation.
- Name boolean values with an affirmative prefix such as `is_`, `has_`, `can_`, or `should_`.
- Name exception classes with a meaningful domain name ending in `Error`.
- Use verb phrases for functions and methods that perform actions; use noun phrases for functions that return values or predicates.
- Test classes use `Test<ProductionSubject>` and test methods use `test_<behavior>_<expected_outcome>`.
- Fixtures and test adapters use descriptive nouns or roles, such as `comfyui_server` and `GimpProcess`.
- Keep I/O at module boundaries so protocol and workflow behavior is unit-testable.
- Raise specific exceptions with actionable messages.
- Do not block the GIMP UI thread; background work belongs behind an explicit worker boundary.
- Keep tests deterministic and avoid network access in unit tests.

## Comments and docstrings

- Write docstrings for public modules, classes, functions, methods, and exceptions when their contract is not obvious from the signature.
- Use comments only to explain non-obvious intent, invariants, external API quirks, or a deliberate tradeoff.
- Do not add comments that narrate straightforward code or repeat the implementation.
- Keep comments concise and place them immediately before the code they explain.
- Update comments and docstrings when behavior changes; stale guidance is worse than no comment.
- Prefer a well-named helper or type over a long explanatory comment.