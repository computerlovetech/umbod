---
type: Software Module
title: Agent behaviour views
description: Administrator-owned definition editors and self-reported report inspection.
---

# Files

- [Page view](AgentBehaviourView.svelte) — Findings landing with collection status and links to System settings.
- [Configuration view](ConfigurationView.svelte) — Standalone diagnostic pattern page with links to reporting settings and findings.
- [Navigation tests](agent-behaviour-navigation.dom.test.ts) — Prop-owned findings, configuration exit, draft preservation and access revocation.
- [Configuration editor](ConfigurationEditor.svelte) — Shared pattern list and revision-aware save or discard for pattern and reporting edits.
- [Reporting settings](ReportingSettings.svelte) — Global reporting switch with saved and draft status, playbook inclusion actions and editable instructions.
- [Instructions state](reporting-instructions-state.svelte.ts) — Tracks which reporting profile’s instructions are open without owning saved values.
- [Reports view](../../shared/agent-behaviour/ReportsView.svelte) — Shared query panel, draft filters, entries, escaped evidence, historical criteria and technical details disclosure.
- [DOM tests](agent-behaviour.dom.test.ts) — Pattern interactions, reporting switch and save behavior, internal identity privacy, report filters and escaped evidence.
