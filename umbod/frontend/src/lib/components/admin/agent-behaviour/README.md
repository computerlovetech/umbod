---
type: Software Module
title: Agent behaviour views
description: Administrator-owned definition editors and self-reported report inspection.
---

# Files

- [Page view](AgentBehaviourView.svelte) — Findings landing with externally owned state and an Agent behaviour heading.
- [Configuration view](ConfigurationView.svelte) — Separate configuration heading, findings backlink and editor dismissal without discarding drafts.
- [Navigation tests](agent-behaviour-navigation.dom.test.ts) — Prop-owned findings, configuration exit, draft preservation and access revocation.
- [Configuration editor](ConfigurationEditor.svelte) — Pattern cards, selected editing, shared polarity dropdown, reporting disclosure and explicit save or discard.
- [Reports view](ReportsView.svelte) — Shared query panel, draft filters, entries, escaped evidence, historical criteria and technical details disclosure.
- [DOM tests](agent-behaviour.dom.test.ts) — Card interactions, hidden settings, internal identity privacy, report filters and escaped evidence.
