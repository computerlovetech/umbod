---
type: Software Module
title: Personal MCP administration composition
description: Actor-owned registration, OAuth policy editing and pre-publication setup workflows using shared controls.
---

# Files

- [PersonalMcpPublicationModal.svelte](PersonalMcpPublicationModal.svelte) — Personal publication consequences and optional access details using shared modal mechanics.

- [PersonalOAuthSetupDialog.svelte](PersonalOAuthSetupDialog.svelte) — Metadata-only readiness, deferred automatic registration and personal sign-in guidance, corrections and publication handoff.
- [PersonalMcpDetails.svelte](PersonalMcpDetails.svelte) — Personal detail lifecycle loads saved setup status independently of check dialogs.
- [personal-oauth-setup-state.svelte.ts](personal-oauth-setup-state.svelte.ts) — Fenced configuration checks, readiness outcomes, correction proposals and in-place publication reconciliation.
- [personal-oauth-setup-state.test.ts](personal-oauth-setup-state.test.ts) — Readiness, no implicit policy writes, revision fencing, pending checks and safe recovery tests.
- [personal-oauth-setup-dialog.dom.test.ts](personal-oauth-setup-dialog.dom.test.ts) — Minimal readiness results, corrective actions, callback reminders and refresh-only unknown outcomes.
- [PersonalServerDiscoveryFields.svelte](PersonalServerDiscoveryFields.svelte) — Guided discovery, permission review and client setup with final issuer approval.
- [personal-server-discovery-state.svelte.ts](personal-server-discovery-state.svelte.ts) — Blur-triggered metadata requests, lifecycle fencing and creation approval ownership.
- [personal-server-discovery-state.test.ts](personal-server-discovery-state.test.ts) — Discovery lifecycle, scope validation, issuer choice and fallback behavior tests.
- [personal-server-registration.dom.test.ts](personal-server-registration.dom.test.ts) — Endpoint discovery, automatic confidential proposals, exact no-secret payloads, approval invalidation and manual fallback tests.
- [PersonalServerRegistration.svelte](PersonalServerRegistration.svelte) — Registration and policy edit forms with immutable server identity.
- [PersonalServerEditDialog.svelte](PersonalServerEditDialog.svelte) — Menu-opened policy editor with injectable metadata discovery and in-place save reconciliation.
- [personal-server-form-state.svelte.ts](personal-server-form-state.svelte.ts) — Registration eligibility, automatic edit discovery, fail-closed policy review and revision-safe settings changes.
- [personal-server-form-state.test.ts](personal-server-form-state.test.ts) — Registration and policy mutation behavior tests.
- [personal-server-edit-dialog.dom.test.ts](personal-server-edit-dialog.dom.test.ts) — Automatic edit discovery, pending/failure gates, backend-proposed methods, manual retention and explicit save tests.
- [PolicyFields.svelte](PolicyFields.svelte) — OAuth application settings and explicit discovered-setting acceptance.
- [policy-form.svelte.ts](policy-form.svelte.ts) — Backend-proposed automatic client transitions, manual settings, edit preservation and safe secret clearing.
- [PersonalServerPolicyPanel.svelte](PersonalServerPolicyPanel.svelte) — Admin-owned OAuth policy and check state alongside user-owned sign-in and discovery.
- [PersonalServerDialog.svelte](PersonalServerDialog.svelte) — Feature dialog composition over shared modal mechanics.
- [modal-dialog.ts](modal-dialog.ts) — Dialog lifecycle integration.
- [form-validation.ts](form-validation.ts) — Native validation integration that clears confidential input.
- [dialog-and-validation.test.ts](dialog-and-validation.test.ts) — Dialog lifetime and native validation behavior tests.
- [personal-servers-components.test.ts](personal-servers-components.test.ts) — Form and policy guidance presentation tests.

# Boundaries

- [Administration contracts](../../../admin/personal-mcp-servers/README.md) — Ports and validated transport adapters.
- [Actor-owned composition](../../../../../../project/architecture-records/ADR-007-actor-specific-ui-composition.md) — Shared presentation versus feature workflow ownership.
