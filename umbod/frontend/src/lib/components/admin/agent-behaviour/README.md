---
type: Software Module
title: Agent behaviour views
description: Administrator-owned definition editors and self-reported report inspection.
---

# Files

- [Page view](AgentBehaviourView.svelte) — Findings landing with collection status and links to Agent diagnostics.
- [Configuration view](ConfigurationView.svelte) — Agent diagnostics heading, subpage navigation and findings link; leaving preserves drafts.
- [Navigation tests](agent-behaviour-navigation.dom.test.ts) — Prop-owned findings, configuration exit, draft preservation and access revocation.
- [Configuration editor](ConfigurationEditor.svelte) — Pattern list with inline inspection and editing, a reporting settings subpage, and shared save or discard.
- [Reports view](../../shared/agent-behaviour/ReportsView.svelte) — Shared query panel, draft filters, entries, escaped evidence, historical criteria and technical details disclosure.
- [DOM tests](agent-behaviour.dom.test.ts) — Pattern interactions, reporting policy and save behavior, internal identity privacy, report filters and escaped evidence.
