---
name: agent-browser-ui-check
description: Use when verifying frontend UI changes in a real browser with agent-browser, including component behavior, visual states, forms, navigation, accessibility-visible controls, console errors, page errors, network failures, screenshots, or browser-based QA.
---

# Agent-browser UI check

Use the native `agent_browser` tool to verify UI changes in a real browser whenever a task changes frontend components, routes, styling, interaction behavior, forms, or browser-side data loading.

## Recommended flow

1. **Start the app in the expected mode**
   - Start the frontend dev server or preview server required by the project.
   - Start dependent services (API, database, mock server, etc.) only when the UI path needs them.
   - Open the browser entrypoint with `agent_browser`, not with shell-driven browser automation.

2. **Open the affected route**
   - Navigate directly to the route that renders the changed UI.
   - If authentication or seeded data is required, use the project’s documented setup path.

3. **Inspect the page with a snapshot**
   - Use a snapshot before interacting.
   - Confirm expected visible text, roles, labels, controls, and important state.
   - Prefer stable locators: role, label, placeholder, text, title, alt text, or test id.
   - Use current snapshot refs only for the same page state; re-snapshot after DOM changes, navigation, or rerenders.

4. **Interact like a user**
   - Use `agent_browser` click/fill/select/check/uncheck actions for standard controls.
   - Batch interactions when they do not submit, navigate, or rerender.
   - For rich text or custom controls, focus/click the editable element and use keyboard/text insertion recovery as needed.
   - Do not use brittle CSS selectors when an accessible locator is available.

5. **Verify resulting UI state**
   - Re-snapshot after interactions and assert the expected text, status, disabled/enabled state, validation message, navigation, or rendered content.
   - For scrollable layouts, verify the actual scroll region moved with a snapshot or screenshot.
   - For native selects, use select actions; for custom comboboxes, re-snapshot after opening options.

6. **Check runtime health**
   - Check for console errors and page errors.
   - Inspect network failures when the component performs browser requests.
   - Treat actionable 4xx/5xx request failures as verification failures unless they are the expected behavior being tested.

7. **Capture visual evidence when useful**
   - Save screenshots for layout, styling, responsive, or visual-regression-sensitive changes.
   - Verify the screenshot artifact path exists before claiming success.

## Lightweight QA shortcut

For simple page checks, use the `agent_browser` QA mode with:
- the target URL,
- expected text or selector,
- console/page/network checks enabled,
- an optional screenshot path for visual evidence.

## Reporting

When reporting verification, state:
- route or URL checked,
- key interactions performed,
- expected UI states observed,
- whether console/page/network checks passed,
- screenshot path if one was captured.
