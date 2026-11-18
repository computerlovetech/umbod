---
type: Software Module
title: Invocation
description: Transport-neutral invocation policy, failure assessment, evidence, and execution workflows.
---

# Files

- [__init__.py](./__init__.py) — Public invocation exports.
- [approval_nonce_store.py](./approval_nonce_store.py) — Approval nonce storage and consumption.
- [diagnostics.py](./diagnostics.py) — Immutable failure diagnostics and downstream response evidence.
- [events.py](./events.py) — Invocation policy change events.
- [failure_assessment.py](./failure_assessment.py) — Shared failure classification, evidence precedence, and connector-origin selection.
- [failure_evidence.py](./failure_evidence.py) — Scoped failure evidence and sanitized exception snapshots.
- [policy.py](./policy.py) — Connector invocation admission and approval policy.
- [policy_store.py](./policy_store.py) — Invocation policy persistence and queries.
- [tools](./tools/) — Tool execution and configuration workflows.
