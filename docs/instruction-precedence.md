# Instruction Precedence

This repository uses several guidance files for different audiences. They do not all have the same authority.

## Precedence order

When rules conflict, apply the first applicable rule in this order:

1. System and developer instructions supplied by the host environment.
2. The user's current request. A newer, explicit request overrides an older repository default.
3. [`AGENTS.md`](../AGENTS.md). This is the authoritative repository contract and wins conflicts between repository guidance files.
4. The most specific applicable `.instructions.md` file under `.github/instructions/`. These files specialize `AGENTS.md` for a path; they must not contradict it.
5. [`.github/copilot-instructions.md`](../.github/copilot-instructions.md). This is the cross-cutting map and default Copilot context.
6. `README.md` files. These explain authoring and usage but do not override normative rules above them.

## Scoped instruction selection

Use the narrowest instruction file that applies to the file being changed:

- `src/**/*.py`: `source.instructions.md`
- `test/unit/**/*.py`, `test/support/**/*.py`, `test/conftest.py`: `unit-tests.instructions.md`
- `test/integration/**/*.py`: `integration-tests.instructions.md`
- `scripts/**/*.py`: `python.instructions.md`

If multiple scoped files apply, combine them. A narrower path-specific rule wins over a broader generic rule only when it remains consistent with `AGENTS.md`. If the conflict cannot be reconciled, follow `AGENTS.md` and ask the user to clarify the intended repository policy.

## Rule-writing policy

- Put repository-wide invariants in `AGENTS.md`.
- Put path-specific practices in the matching `.instructions.md` file.
- Put contributor rationale, examples, and setup details in `CONTRIBUTING.md`; put product usage and installation details in `README.md`.
- Do not duplicate a rule across files unless the duplicate is a deliberate pointer to the authoritative rule.
- When changing precedence or ownership, update this document and the affected instruction index together.