---
name: umbod-agent-behaviour
description: >
  Apply Umbod's permission-aware obstacle reporting playbooks. Use when encountering difficulties.
---

# Umbod agent behaviour

## Outcome

Obstacles follow current playbooks without unauthorized or duplicate diagnostic reports.

## Inputs

- Required: An obstacle and current selected playbook instructions before self-reporting.
- Optional: Existing user/client reporting authority, prior payload, UUID key, and durable receipt.
- Default: Do not report without proactive permission and user/client authority.

## Rules

- R1: Read current selected playbook instructions before self-reporting.
- R2: Preserve schema, privacy, and exactly-once pattern assessment.
- R3: Never claim reporting success without a durable receipt.

## Workflow

1. Discover Umbod's agent-behaviour playbooks at `umbod://agent-behaviour/playbooks` and read the selected playbook's current instructions before self-reporting obstacles.
2. Call `report_diagnostic` with `trigger=proactive` only when the playbook allows proactive reporting and the user and client authorize it, otherwise do not submit a report.
3. Follow the current reporting schema and privacy guidance, assess every selected pattern exactly once, and include only short factual summaries without transcripts, secrets, credentials, or hidden reasoning.
4. Generate one UUID idempotency key before submission, retry uncertain outcomes only with the identical payload and key, and claim success only after receiving a durable receipt.

## Decisions

| Condition | Action |
|---|---|
| Playbook instructions or reporting permission are unavailable | Do not submit; do not seek reporting authority merely because an obstacle occurred. |
| Prior submission details are absent | Generate one UUID key for a new authorized submission. |
| Submission outcome is uncertain | Retry only with identical payload/key; otherwise report uncertainty. |
| Recovery fails | Stop attempts and report the blocker without claiming success. |

## Output

Return:
- Short factual obstacle or reporting status.
- Durable receipt confirmation or explicit uncertainty/non-submission.
- Unresolved blockers without private data or hidden reasoning.

## Completion criteria

- Current playbook, permissions, schema, and privacy were respected.
- Every selected pattern was assessed once; uncertain retries preserve payload/key identity.

## References

- None required.
