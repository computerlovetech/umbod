---
type: Software Module
title: Personal MCP administration composition
description: Actor-owned registration, OAuth policy editing and pre-publication setup workflows using shared controls.
---

# Files

- [PersonalOAuthSetupPanel.svelte](PersonalOAuthSetupPanel.svelte) — Saved setup status, explicit discovery, scope approval and validation; no personal login.
- [personal-oauth-setup-state.svelte.ts](personal-oauth-setup-state.svelte.ts) — Fenced setup requests, explicit policy saves and in-place publication reconciliation.
- [personal-oauth-setup-state.test.ts](personal-oauth-setup-state.test.ts) — Scope mismatch, revision-safe approval, disposal, pending and safe failure tests.
- [personal-oauth-setup-panel.dom.test.ts](personal-oauth-setup-panel.dom.test.ts) — Unchecked candidate, explicit approval, validation and failure interaction tests.
- [PersonalServerRegistration.svelte](PersonalServerRegistration.svelte) — Registration and policy edit forms with immutable server identity.
- [PersonalServerEditDialog.svelte](PersonalServerEditDialog.svelte) — Menu-opened policy editor and in-place save reconciliation.
- [personal-server-form-state.svelte.ts](personal-server-form-state.svelte.ts) — Registration and revision-safe policy editing state.
- [personal-server-form-state.test.ts](personal-server-form-state.test.ts) — Registration and policy mutation behavior tests.
- [personal-server-edit-dialog.dom.test.ts](personal-server-edit-dialog.dom.test.ts) — Policy editing, explicit discovery suggestions and cancellation interaction tests.
- [PolicyFields.svelte](PolicyFields.svelte) — OAuth application settings and explicit discovered-setting acceptance.
- [policy-form.svelte.ts](policy-form.svelte.ts) — Application settings form and safe secret clearing.
- [PersonalServerPolicyPanel.svelte](PersonalServerPolicyPanel.svelte) — Group access and owner authorization guidance.
- [PersonalServerDialog.svelte](PersonalServerDialog.svelte) — Feature dialog composition over shared modal mechanics.
- [modal-dialog.ts](modal-dialog.ts) — Dialog lifecycle integration.
- [form-validation.ts](form-validation.ts) — Native validation integration that clears confidential input.
- [dialog-and-validation.test.ts](dialog-and-validation.test.ts) — Dialog lifetime and native validation behavior tests.
- [personal-servers-components.test.ts](personal-servers-components.test.ts) — Form and policy guidance presentation tests.

# Boundaries

- [Administration contracts](../../../admin/personal-mcp-servers/README.md) — Ports and validated transport adapters.
- [Actor-owned composition](../../../../../../project/architecture-records/ADR-007-actor-specific-ui-composition.md) — Shared presentation versus feature workflow ownership.
