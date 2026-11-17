---
type: Operational Reference
title: Ordered effect review
description: Decision sequence for accepting or removing a Svelte effect.
---

# Ordered effect review

Answer in order before adding or retaining an effect:

1. Can a single source of truth be read directly from `page.url`, props, or store state?
2. Can `$derived` replace mirrored mutable state?
3. Can an explicit click, submit, or navigation handler own the change?
4. Would the effect introduce two-way synchronization or hidden coupling?
5. Is the remaining side effect external and intentional: I/O, an imperative API, or subscription lifecycle?

If any of the first three suffices, do not use an effect. Prefer URL-first or model-first ownership, controlled `value` + `onChange` components, and one-way commands.

For every retained effect, state why derivation cannot work, why an event handler is insufficient, and what guard prevents loops or redundant writes. Check idempotence and teardown for subscriptions and owned resources. If the justification cannot be given, stop and refactor away from the effect.
