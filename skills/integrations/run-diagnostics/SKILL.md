---
name: run-diagnostics
description: >
  Run an Umbod diagnostic self-assessment. Use when the user explicitly requests diagnostics, not merely when an obstacle occurs.
---

# Run diagnostics

## Outcome

Follow the current Umbod playbook for a user-requested diagnostic assessment.

## Inputs

- Required: An explicit user request to run diagnostics and access to Umbod MCP resources.
- Optional: The user's choice of playbook.
- Default: Select the only enabled playbook if no choice was supplied.

## Rules

- R1: Use this skill only for user-requested diagnostics, never proactive reporting.
- R2: Read the selected live resource before assessing or submitting; do not substitute cached instructions.
- R3: Follow its server-owned reporting guidance, including privacy and receipt requirements.

## Workflow

1. Read `umbod://agent-behaviour/playbooks` from the Umbod MCP server.
2. Select the requested or sole enabled playbook; ask the user to choose if several are available and none was specified.
3. Read the selected `resource_uri` from the index and follow its live guidance. Submit using `report_diagnostic` with `trigger=user_requested` only if the tool is available.
4. Confirm whether the write returned a durable receipt before reporting success.

## Decisions

| Condition | Action |
|---|---|
| The user did not request diagnostics | Do not submit a report. |
| The requested playbook is not enabled | Ask the user to choose an enabled playbook, if any are available. |
| The server rejects the submission or the outcome is uncertain | Follow the live reporting guidance and the tool's corrective instructions. |
| The live tool, playbook, or resource is unavailable | Stop without submitting or using cached instructions; explain the blocker. |

## Output

Return:
- Whether the diagnostic report was submitted.
- The report ID if a durable receipt was returned.
- Any blocker or unresolved submission outcome.

## Completion criteria

- The selected playbook was read live and its reporting guidance was followed.
- No submission is described as successful without a durable receipt.

## References

- None required.
