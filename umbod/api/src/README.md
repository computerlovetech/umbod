---
type: Software Module
title: Backend source
description: API, MCP, CLI, and shared application services.
---

# Files

- [REST](umbod/rest/README.md) — HTTP endpoints, including authenticated filesystem browsing and breadcrumbs.
- [MCP](umbod/mcp/README.md) — Tool server.
- [CLI](umbod/cli/README.md) — Commands.
- [Core](umbod/core/README.md) — Application logic.
- [Configuration](umbod/config/README.md) — Runtime settings.
- [Build identity](umbod/build_identity.py) — Immutable release and revision stamped during image builds, with explicit source-development defaults.
- [HTTP metadata](umbod/http_metadata.py) — Streaming-safe release headers and request-local correlation across REST and MCP.
- [Shared logging](umbod/logging.py) — Failure signal composition, logging receivers, and bounded JSON output.
- [Application diagnostics](../../docs/operations/application-diagnostics.md) — Field contracts, privacy rules, and failure investigation.
- [Hosting](umbod/hosting/README.md) — Service startup.
- [Infrastructure](umbod/infrastructure/README.md) — External adapters.
- [Messaging](messaging/README.md) — Events.
