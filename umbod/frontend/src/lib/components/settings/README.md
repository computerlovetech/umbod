---
type: Software Module
title: Settings components
description: Account navigation, read-only profile and personal access token management.
---

# Files

- [SettingsFrame.svelte](./SettingsFrame.svelte) — Account hero, breadcrumb and grouped navigation.
- [AccountProfile.svelte](./AccountProfile.svelte) — Visible account picture, display name and email.
- [SettingsHarness.test-support.svelte](./SettingsHarness.test-support.svelte) — Workspace context fixture for profile rendering tests.
- [PersonalTokens.svelte](./PersonalTokens.svelte) — Token list with permission filtering, expiration dates, and deletion.
- [PersonalTokenDialog.svelte](./PersonalTokenDialog.svelte) — Token creation form and one-time token reveal.
- [personal-token-state.svelte.ts](./personal-token-state.svelte.ts) — Permission mapping, token lifecycle, and transient secrets.
- [personal-token-state.test.ts](./personal-token-state.test.ts) — Token lifecycle, failures, and obsolete-result tests.
- [personal-tokens.dom.test.ts](./personal-tokens.dom.test.ts) — Permission filtering, modal creation, token copying, deletion, and access eligibility.
