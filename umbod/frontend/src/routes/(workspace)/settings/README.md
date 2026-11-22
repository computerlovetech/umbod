---
type: Software Module
title: Account settings routes
description: Personal settings within the authenticated workspace frame.
---

# Files

- [+layout.svelte](./+layout.svelte) — Shared account settings frame and current destination.
- [+page.svelte](./+page.svelte) — Read-only profile using the effective workspace identity.
- [Access tokens page](./tokens/+page.svelte) — Creation and management of personal access tokens.
- [Settings components](../../../lib/components/settings/README.md) — Profile, account navigation, and token management.
- [settings.test.ts](./settings.test.ts) — Breadcrumbs, destination links, profile visibility and the token anchor.
- [Route tests](../../navigation.test.ts) — Workspace recognition and legacy telemetry redirect.
