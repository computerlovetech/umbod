---
name: run-diagnostics
description: >
  Run an Umbod diagnostic self-assessment. Use when the user requests diagnostics or a concrete obstacle warrants one.
---

# Run diagnostics

## Outcome

Assess a concrete issue using Umbod’s current playbook and submit only an authorized report.

## Inputs

- Required: A user request or concrete obstacle, and access to Umbod’s live diagnostic resources.
- Optional: The user’s choice of playbook and any existing reporting authorization or submission receipt.
- Default: Select the sole enabled playbook if none was specified. Do not assume authorization to submit a proactive report.

## Rules

- R1: Use `trigger=user_requested` for explicit requests and `trigger=proactive` for agent-initiated diagnostics. The trigger does not grant permission: submit only if authorized by the user and client and allowed by the live collection instructions.
- R2: Read the selected live playbook before assessing or submitting. Follow its schema and privacy guidance; use brief factual summaries, never transcripts, secrets, credentials, or hidden reasoning.
- R3: Assess each selected pattern once. Use a new UUID for each new submission, retry only with the identical payload and key, and claim success only with a durable receipt.

## Workflow

1. Read `umbod://agent-behaviour/playbooks` from the Umbod MCP server.
2. Select the requested or sole enabled playbook. If several are enabled and none was specified, ask which one to use.
3. Read the selected `resource_uri` and follow its current instructions. If reporting is authorized and the live `report_diagnostic` tool is available, submit with the appropriate trigger.
4. Verify the durable receipt before confirming submission.

## Decisions

| Condition | Action |
|---|---|
| Proactive reporting is not authorized | Do not submit; explain the obstacle if it affects the user’s task. |
| The requested playbook is not enabled | Ask the user to choose an enabled playbook, if any are available. |
| Submission is rejected or uncertain | For a rejection, follow the tool’s corrective guidance; if stale, reload the playbook and reassess. If the outcome is uncertain, retry only with the identical payload and key. |
| Live instructions are unavailable or recovery remains blocked | Stop without falling back to cached instructions; report the blocker or uncertainty. |

## Output

Return:
- Whether the diagnostic report was submitted.
- The report ID if a durable receipt was returned.
- Any blocker or unresolved submission outcome, without private data.

## Completion criteria

- The selected live playbook, authorization, schema, and privacy requirements were respected.
- Every selected pattern was assessed once; any retry preserved the payload and key, and success was backed by a durable receipt.

## References

- None required.
