---
name: agent-browser-ui-check
description: >
  Verify frontend changes in a real browser with agent-browser. Use when checking component behavior, visual states, forms, navigation, accessible controls, console or page errors, network failures, screenshots, or browser-based QA.
---

# Agent-browser UI check

## Outcome

Affected UI behavior is verified in a running application with browser evidence and explicit limitations.

## Inputs

- Required: Changed UI behavior, application setup instructions, and verification target.
- Optional: Supplied OpenAPI configuration, expected visual states, and existing evidence.
- Default: Use the general UI flow; load only references relevant to the affected behavior.

## Rules

- R1: Use the native agent_browser tool for real-browser verification; repository setup and verification requirements override generic guidance.
- R2: Choose the flow from affected behavior; do not load OpenAPI endpoint guidance for unrelated UI tests.
- R3: Inspect actual behavior, runtime health, and evidence; report failures and unverified states without claiming success.

## Workflow

1. Identify affected behavior and follow repository instructions to start the application and select its running URL.
2. Read references/browser-verification.md for general changes; for a simple smoke check read its lightweight QA and reporting sections first.
3. For OpenAPI configuration, specification discovery, or live execution, also read references/openapi-connectors-ui.md; load its endpoint reference only when needed.
4. Run the selected checks, inspect evidence and runtime health, investigate failures with the full checklist, and report observed results.

## Decisions

| Condition | Action |
|---|---|
| General UI behavior changes | Use the general browser-verification flow. |
| OpenAPI configuration or execution changes | Use the OpenAPI guide and browser checklist with supplied configuration or public test endpoints. |
| OpenAPI changes affect only layout or styling | Use the general flow unless verification requires API configuration or execution. |
| Smoke checks reveal failures or need interactions or visual inspection | Apply the full browser checklist; report unresolved blockers. |

## Output

Return:
- Browser flows checked and observed results.
- Verified evidence and runtime-health findings.
- Failures, blockers, and unverified states.

## Completion criteria

- Applicable repository requirements and selected browser checks pass with inspected evidence.
- Failures and verification limits are explicit; irrelevant endpoint guidance was not loaded.

## References

- Read `references/browser-verification.md` when checking setup, interaction, state, runtime health, evidence, or reporting.
- Read `references/openapi-connectors-ui.md` when verifying OpenAPI configuration, discovery, or live execution.
