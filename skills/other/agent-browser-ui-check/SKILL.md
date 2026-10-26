---
name: agent-browser-ui-check
description: Use when verifying frontend UI changes in a real browser with agent-browser, including component behavior, visual states, forms, navigation, accessibility-visible controls, console errors, page errors, network failures, screenshots, or browser-based QA.
---

# Agent-browser UI check

Use the native `agent_browser` tool for real-browser verification of frontend changes. Follow repository instructions for app setup and required verification; these take precedence over generic guidance below.

## Select the test flow

Choose from the task context and affected behavior. Read only the references needed for that flow; paths are relative to this skill directory.

- **General UI changes:** Read `references/browser-verification.md` for setup, interaction, state verification, runtime health, evidence, and reporting.
- **OpenAPI connector UI configuration, specification discovery, or live execution:** Read `references/openapi-connectors-ui.md` and the browser checklist in `references/browser-verification.md`. The OpenAPI guide selects supplied API configuration or public test endpoints; load its endpoint reference only when needed.
- **Simple page smoke checks:** Read the lightweight QA and reporting sections of `references/browser-verification.md`. Use the full checklist when interactions, visual inspection, or failures need investigation.

For OpenAPI connector changes limited to layout or styling, use the general UI flow unless verification requires API configuration or execution. Do not load OpenAPI endpoint guidance for unrelated UI tests.
