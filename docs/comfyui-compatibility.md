# ComfyUI Compatibility

This plug-in currently targets ComfyUI's API-format workflow and REST endpoints. The compatibility record is deliberately separate from the implementation so protocol changes have an explicit review point.

## Validated baseline

- ComfyUI 0.34.0 has been validated with the opt-in health and generation flows.
- The current client uses `/system_stats`, `/object_info`, `/prompt`, `/history/{prompt_id}`, `/view`, `/upload/image`, `/interrupt`, and `/queue`.
- Workflow submissions must be API-format node maps. UI-format workflow exports are rejected locally.
- Custom-node workflows are supported only when the configured ComfyUI instance provides every referenced node and input.

## Protocol cautions

DeepWiki's upstream ComfyUI reference identifies global `/interrupt` and queue mutation endpoints as deprecated in favor of prompt-specific job APIs. They remain the compatibility baseline for the current client, but new cancellation behavior must not assume they are the long-term contract.

Before changing the client to a newer job API, verify the endpoint and response schema against the target ComfyUI version, add local fake-server tests, and add an opt-in live cancellation flow. Keep the legacy path available until the supported-version matrix confirms the replacement.

WebSocket events are the preferred future path for progress and completion notifications. The planned WebSocket work must define handling for `status`, `progress`, `executing`, `executed`, cached execution, previews, and `execution_error` messages before it replaces REST polling.

## Test expectations

- Unit tests use the local HTTP fake and must cover response parsing, HTTP failures, malformed JSON, cancellation, and endpoint-specific request payloads.
- Integration tests are opt-in and must declare their required ComfyUI version, workflow, checkpoint, custom nodes, and environment variables.
- `object_info` discovery should be used to validate resource names and required node inputs before queueing user work where practical.
- DeepWiki is a supplemental upstream reference, not a substitute for the local fake, a configured live flow, or the official ComfyUI source/API schema.