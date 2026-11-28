---
type: Software Module
title: Administrator agent token client
description: Validated HTTP contracts for managing public MCP agent credentials.
---

# Source

- [Schemas](./domain/schemas.ts) — Request and response contracts for the agent token lifecycle.
- [Port](./port.ts) — Agent token operations used by the administration workspace.
- [HTTP routes](./http-route.ts) — Admin route adapter over the shared transport.
- [Route tests](./http-route.test.ts) — Wire validation and lifecycle route coverage.
