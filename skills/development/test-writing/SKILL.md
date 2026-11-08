---
name: test-writing
description: >-
  Guides writing and refactoring tests across pytest, Vitest and Kind integration
  tests. Use when adding tests, changing fixtures or assertions, choosing test
  boundaries, or reviewing test coverage and quality.
---

# Test writing

Before writing or changing a test, identify the behavior and test boundary, then read the relevant reference below. Read more than one when they apply; do not load unrelated references.

| Test being written | Required reference |
| --- | --- |
| Python unit, adapter, contract or in-process application tests | [Pytest practices](references/pytest.md) |
| TypeScript or JavaScript unit tests, reactive state tests or Svelte DOM tests | [Vitest practices](references/vitest.md) |
| Tests against running services in a Kind cluster | [Kind integration practices](references/kind-integration.md) and [pytest practices](references/pytest.md) |

For real-browser UI checks, also load the [agent-browser-ui-check skill](../../../skills/other/agent-browser-ui-check/SKILL.md). DOM tests do not establish real-browser layout or deployed behavior.

Choose the smallest boundary that proves the behavior. Add deployed integration coverage when the risk depends on real service wiring or cross-process behavior, rather than duplicating every unit scenario.

Follow the repository's `AGENTS.md` verification requirements independently. A requirement to run a suite does not by itself mean every change needs a new integration test.
