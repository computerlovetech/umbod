---
type: Software Module
title: File preview state and ports
description: Cancellable file content loading and replaceable filetype renderer contracts.
---

# Preview

- [ports.ts](./ports.ts) — Content acquisition and component adapter ports with an explicitly composed filetype resolver.
- [file-preview-state.svelte.ts](./file-preview-state.svelte.ts) — Read eligibility, loading, retries, empty and failure states with stale-result fencing.
- [file-preview-state.test.ts](./file-preview-state.test.ts) — Content loading, permission isolation, cancellation, retry and filesystem navigation behavior.
- [in-memory-content.test-support.ts](./in-memory-content.test-support.ts) — Test-only injectable content source recording requests and abort signals.
