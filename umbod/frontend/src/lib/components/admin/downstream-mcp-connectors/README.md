---
type: Software Module
title: MCP connector administration components
description: Shared and personal MCP workspaces, confirmation-owned mutations, and capability controls.
---

# Files

- [DownstreamMcpPageContent.svelte](./DownstreamMcpPageContent.svelte) — Page composition, registration, and mutation disposal.
- [DownstreamMcpWorkspace.svelte](./DownstreamMcpWorkspace.svelte) — Connector selection, action menus, confirmation, and operation feedback.
- [downstream-mcp-workspace-state.svelte.ts](./downstream-mcp-workspace-state.svelte.ts) — Selection and setup state; publication requests retain connector identity, not menu forms.
- [downstream-mcp-workspace-state.test.ts](./downstream-mcp-workspace-state.test.ts) — Selection, mutation gates, and confirmation state tests.
- [downstream-mcp-mutation-state.svelte.ts](./downstream-mcp-mutation-state.svelte.ts) — Confirmed API mutations, loading, safe failures, and authoritative reloads.
- [downstream-mcp-publication.dom.test.ts](./downstream-mcp-publication.dom.test.ts) — Mounted-workspace publication, withdrawal, cancellation, duplicate submission, and failure regressions.
- [DownstreamMcpSetupModal.svelte](./DownstreamMcpSetupModal.svelte) — Shared connector creation and configuration.
- [DownstreamMcpToolCatalog.svelte](./DownstreamMcpToolCatalog.svelte) — Discovered tool catalogue and batch controls.
- [DownstreamMcpToolActivationToggle.svelte](./DownstreamMcpToolActivationToggle.svelte) — Tool activation control.
- [downstream-mcp-tool-catalog-state.svelte.ts](./downstream-mcp-tool-catalog-state.svelte.ts) — Tool activation and invocation-policy changes.
- [downstream-mcp-tool-catalog-state.test.ts](./downstream-mcp-tool-catalog-state.test.ts) — Tool catalogue mutation and reconciliation tests.
- [DownstreamMcpPromptCatalog.svelte](./DownstreamMcpPromptCatalog.svelte) — Prompt catalogue and activation controls.
- [downstream-mcp-prompt-catalog-state.svelte.ts](./downstream-mcp-prompt-catalog-state.svelte.ts) — Prompt activation changes and reconciliation.
- [downstream-mcp-prompt-catalog-state.test.ts](./downstream-mcp-prompt-catalog-state.test.ts) — Prompt mutation and reconciliation tests.
- [DownstreamMcpResourceCatalog.svelte](./DownstreamMcpResourceCatalog.svelte) — Resource catalogue and activation controls.
- [downstream-mcp-resource-catalog-state.svelte.ts](./downstream-mcp-resource-catalog-state.svelte.ts) — Resource activation changes and reconciliation.
