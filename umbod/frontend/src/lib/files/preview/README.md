---
type: Software Module
title: File preview state and ports
description: Cancellable file content loading and replaceable filetype renderer contracts.
---

# Preview

- [configuration.ts](./configuration.ts) — Validated preview byte-limit contract and injectable configuration provider.
- [in-memory-configuration.test-support.ts](./in-memory-configuration.test-support.ts) — Test-only configuration provider for nondefault size limits and validation.
- [ports.ts](./ports.ts) — Content acquisition and component adapter ports with an explicitly composed filetype resolver.
- [file-preview-state.svelte.ts](./file-preview-state.svelte.ts) — Configured size presentation, read eligibility, retries and read/render failures with stale-result fencing.
- [file-preview-state.test.ts](./file-preview-state.test.ts) — Content loading, permissions, cancellation, retry, stale render failures and filesystem navigation behavior.
- [in-memory-content.test-support.ts](./in-memory-content.test-support.ts) — Test-only injectable content source recording requests and abort signals.
