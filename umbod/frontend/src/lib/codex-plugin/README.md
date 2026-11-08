---
type: Software Module
title: Codex plugin downloads
description: Validated endpoint-specific Codex marketplace archives built from the canonical Python package template.
---

# Files

- [contracts.ts](./contracts.ts) — Endpoint validation, archive contracts, and packaging and browser-download ports.
- [browser-package.ts](./browser-package.ts) — SHA-256 marketplace identity, canonical template specialization, ZIP encoding, and Blob download cleanup.
- [package-template.json](./package-template.json) — Generated distribution artifact; regenerate with the Python builder rather than editing it directly.
- [Python package builder](../../../../scripts/build_codex_plugin.py) — Canonical manifest, skill, license, and browser-template generation.
- [Installation and regeneration](../../../../docs/using-umbod/codex-plugin.md) — Dashboard and terminal installation, authentication, lifecycle, and template regeneration.

# Verification

- [browser-package.test.ts](./browser-package.test.ts) — Archive entries, canonical skill and license, endpoint safety, and deterministic marketplace identities.
- [browser-download.dom.test.ts](./browser-download.dom.test.ts) — Browser download dispatch, filename and MIME type, and anchor and Blob URL cleanup on success or failure.
- [in-memory.test-support.ts](./in-memory.test-support.ts) — Test-only packaging and download adapters for onboarding state and DOM tests.
