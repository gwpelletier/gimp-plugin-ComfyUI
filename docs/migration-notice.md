# Migration Notice

This repository is now distributed under the GNU General Public License, version 3 only (GPL-3.0-only).

The migration source is:

- Repository: `gimp-comfy-tools`
- Local path: `/home/frank/repos/personal/gimp-comfy-tools`
- Source license: GPL-3.0-only
- Upstream author recorded in the source repository: Grant Pelletier

Functionality migrated from that project must retain GPL-3.0-only licensing and appropriate attribution. Significant migrated or modified files should identify the migration in their history or file notice where practical.

The source repository contains vendored copies of `requests`, `websocket-client`, `urllib3`, `certifi`, `charset-normalizer`, and `idna`. Those third-party packages are not automatically included in this migration. Their license and packaging obligations must be reviewed separately before any of them are added to this plug-in bundle.

The current migration preserves the target project's boundary design:

- GIMP and GTK code belongs at the plug-in/UI boundary.
- ComfyUI HTTP and WebSocket behavior belongs in `src/comfyui_plugin/client.py`.
- Workflow transformation and persistence belong in non-GIMP modules where possible.

Migrated capabilities currently include ComfyUI health/queue/history/view/upload operations, node metadata discovery, workflow parameter preparation, LoRA chain injection, user workflow registration, JSON persistence, asynchronous generation coordination, and GIMP result-layer insertion. The source project's richer gallery, style/history, mask, and WebSocket-preview UI remains a follow-up migration area.