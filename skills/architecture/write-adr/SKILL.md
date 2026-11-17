---
name: write-adr
description: >
  Write a concise Architecture Decision Record and keep the AGENTS.md ADR index current. Use when explicitly invoked by the user only.
disable-model-invocation: true
---

# Write an Architecture Decision Record

## Outcome

An explicitly requested ADR records a factual decision and keeps the architecture index synchronized.

## Inputs

- Required: Explicit user invocation, consequential decision, and essential rationale.
- Optional: Established acceptance, owners, advice, evidence, and related records.
- Default: Use Proposed status; label material unknowns and omit inapplicable optional fields.

## Rules

- R1: Apply only when explicitly invoked by the user; read references/guide.md completely before applying. Writing an ADR never authorizes implementation.
- R2: Never invent rationale, evidence, alternatives, advice, owners, confidence, or approval; use Accepted only when team acceptance is established.
- R3: Preserve accepted text; changes require a new ADR. On accepted replacement, synchronize dated supersession links both ways and the root AGENTS.md index.

## Workflow

1. Confirm explicit invocation, read the complete guide, repository instructions, and related ADRs; ask about missing decisions or essential rationale.
2. Use the next number after the highest existing ADR and the repository location; draft with the guide's existing template, defaulting to Proposed.
3. Preserve accepted records; update lifecycle metadata for accepted replacements and synchronize exactly one numbered index entry per ADR, including statuses and reading guidance.
4. Review brevity, factual accuracy, template coverage, bidirectional supersession links, and every ADR/index link; report unresolved questions.

## Decisions

| Condition | Action |
|---|---|
| Explicit invocation, decision, or essential rationale is missing | Do not create a record; ask for the missing authorization or facts. |
| Acceptance or optional metadata is absent | Use Proposed, label material unknowns, and omit inapplicable fields. |
| Review finds invented claims or index/link mismatches | Remove unsupported claims, repair synchronization, and rerun review. |
| Recovery fails | Stop the affected ADR work and report the blocker without inventing consensus. |

## Output

Return:
- Changed ADR and root AGENTS.md paths.
- Factual, template, lifecycle, index, and link review results.
- Unresolved questions and implementation authorization limitations.

## Completion criteria

- The explicitly requested record uses grounded content and established status without rewriting accepted decisions.
- All records have current index entries; applicable supersession links and dates agree in both directions.

## References

- Read `references/guide.md` when applying this skill; the full workflow and existing ADR template are mandatory. Command paths remain skill-root-relative; repository paths retain their repository-relative meaning.
