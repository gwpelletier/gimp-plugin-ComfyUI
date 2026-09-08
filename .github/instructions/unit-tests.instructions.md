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

## Test value requirement

Every test must assert an observable behavior that a caller can rely on. A test that would still pass after a real regression in the asserted behavior is worthless and must not be written. Coverage is a floor, not a goal: never write a test only to execute a line.

Worthless tests to avoid:

- Asserting only that something does **not** happen (no exception, no call, `result is not None`) without asserting what **does** happen.
- Asserting on mock internals or private state instead of the public outcome.
- Re-implementing the production logic in the assertion so the test always agrees with itself.

Good example — asserts the observable outcome of a failure path:

```python
def test_read_exact_returns_error_when_socket_closes_mid_frame(self):
    # Arrange
    socket_pair = FakeSocketPair()
    socket_pair.server.sendall(b"\x81")  # header byte, then close before the length byte
    socket_pair.server.close()
    transport = ComfyUIWebSocket("ws://localhost/ws", client_id="test")
    transport._socket = socket_pair.client

    # Act / Assert
    with pytest.raises(ComfyUIError, match="closed unexpectedly"):
        transport.receive()
```

Bad example — worthless: it only asserts nothing exploded and would pass even if `receive` dropped the event:

```python
def test_receive_handles_text_frame(self):
    transport.receive()  # must not raise
```

Bad example — worthless: it asserts a negative without pinning the positive contract:

```python
def test_connect_rejects_bad_upgrade(self):
    with pytest.raises(ComfyUIError):
        transport.connect()
    assert transport._socket is None  # private state, no caller-observable behavior asserted
```

When in doubt, ask: "If someone broke this behavior tomorrow, which assertion fails?" If the answer is none, delete the test or rewrite it to assert the real contract.

Mutation testing (`python scripts/run_mutation.py`, see `CONTRIBUTING.md`) is the executable form of that question: a surviving mutant means the tests tolerated a behavior change, so add or strengthen the assertion that kills it. `mutmut` does not run on native Windows, so the runner wraps it in a Docker container; run mutmut directly only on Linux/macOS.