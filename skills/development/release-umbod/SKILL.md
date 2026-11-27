---
name: release-umbod
description: >
  Prepare and verify an immutable Umbod release and live publication. Use when the user explicitly invokes release preparation or publication.
disable-model-invocation: true
---

# Release Umbod

## Outcome

An approved immutable tag/SHA publishes verified artifacts and matching Cloudflare production.

## Inputs

- Required: Explicit user invocation, intended stable or beta version, and exact tag/SHA approval before publication.
- Optional: Release scope, prepared content, and existing verification evidence.
- Default: Prepare and verify only until the exact tag and SHA are approved; never infer a version or approval.

## Rules

- R1: Run only on explicit user invocation; installation is not authorization. Preserve unrelated work and require approval of the final tag/SHA.
- R2: Require main ancestry, exact successful main CI, preview checks, and production fast-forward eligibility; use the release workflow to promote production.
- R3: Publish one immutable tag only; block collisions and lookup errors. Never move tags, overwrite artifacts, force production, run concurrent releases, or blindly retry.

## Workflow

1. Read references/release-procedure.md fully before working; recheck workflows, permissions, protection, Cloudflare, and current releases.
2. Prepare content and committed metadata; follow references/verification.md, freeze RELEASE_SHA on main, and verify ancestry, CI, preview, and destinations.
3. Obtain exact tag/SHA approval with evidence; recheck state, tag that SHA, push only that tag, and watch the workflow.
4. Verify SDK, images/architectures, chart, production SHA, Cloudflare, and live production/preview; report each checkpoint.

## Decisions

| Condition | Action |
|---|---|
| Invocation, version, or exact publication approval is missing | Ask for it; do not publish or guess. |
| Scope or evidence is omitted | Inspect current release changes and executable behavior; prepare and verify first. |
| A gate or publication check fails | Stop, inspect partial publication and diagnostics, and use only the guide's safe recovery. |
| Recovery cannot safely resume | Report the blocker and agree a fresh version after fixes; never reuse or move the old tag. |

## Output

Return:
- Tag/SHA, resolved versions, approved content changes, and release-run URL/conclusion.
- Artifact versions/digests, production SHA, Cloudflare evidence, and live production/preview results.
- Warnings, skips, failures, pending checkpoints, and owners.

## Completion criteria

- Publication used only the approved immutable tag/SHA and all required gates passed.
- Artifacts and the actual live deployment are verified; pending checkpoints are never called complete.

## References

- Read `references/release-procedure.md` when explicitly invoked, before task work; all safety and recovery steps are mandatory.
- Read `references/verification.md` when preparing the candidate and verifying published artifacts.
