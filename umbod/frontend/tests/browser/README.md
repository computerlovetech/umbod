---
type: Software Module
title: Safari connector layout checks
description: Opt-in Safari tests for connector dialog focus and rendered field clearance.
---

# Files

- [Connector layout tests](./connector-layout.safari.test.ts) — Checks spacing before and after field focus on the running app; requires Safari remote automation and supports UMBOD_UI_TEST_URL.
- [Safari runner](../../vite.safari.config.ts) — Run with bun run test --config vite.safari.config.ts; separate from ordinary unit tests because it opens Safari.
