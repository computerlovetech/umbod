---
name: write-adr
description: Write a concise Architecture Decision Record and keep the AGENTS.md ADR index current. Use only when explicitly invoked by the user.
disable-model-invocation: true
---

# Write an Architecture Decision Record

Capture one consequential decision and why it made sense at the time, not an implementation plan. Aim for one page, at most two. Use plain language and an inverted pyramid: decision first, explanation next, supporting detail linked rather than embedded. Use drafting to expose disagreements, not manufacture consensus.

## Workflow

1. Read repository instructions and related ADRs; identify conflicts or decisions this record would replace. Ask about missing decisions or essential rationale. Never invent evidence, alternatives considered, advice, owners, confidence, or approval; label material unknowns.
2. Write to `umbod/project/architecture-records/ADR-NNN-short-decision-title.md`, using the next number after the highest existing number. Do not reuse gaps or renumber records. In other repositories, follow their existing location and naming convention.
3. Fill the template below, preserving local metadata conventions. Remove inapplicable optional fields and sections. Default to **Proposed** (under discussion); use **Accepted** (active) only when team acceptance is established.
4. Preserve accepted decision text. A changed decision needs a new ADR, not a rewrite. When its replacement is accepted, mark the old record **Superseded**, date the transition, and link the records in both directions through lifecycle metadata.
5. Synchronize the root `AGENTS.md` architecture decisions index with every ADR in the directory: exactly one entry per record, ordered by number, using the ADR number and title as link text and a working relative path. Include all statuses, label non-accepted records, and preserve existing reading guidance. Add missing entries and refresh stale titles, links, and statuses.
6. Review for brevity, factual accuracy, complete template coverage, and valid links in both the ADR and index. Report changed paths and unresolved questions. Writing an ADR does not authorize implementation.

## Template

```markdown
# ADR-[NNN]: [Short title stating the decision]

- **Status:** Proposed
- **Date:** [YYYY-MM-DD]
- **Decision owners:** [Responsible people or team, if known]
- **Scope:** [Product, subsystem, or ecosystem boundary]
- **Supersedes:** [Relative link, if applicable]
- **Superseded by:** [Relative link, if applicable]
- **Status changed:** [YYYY-MM-DD, if applicable]

## Decision

[State the choice and where it applies, understandable without the remaining sections.]

## Context and rationale

[Describe the problem, facts, constraints, and competing forces. Explain why this choice best balances them. Distinguish evidence from assumptions.]

## Alternatives considered

[For every serious alternative actually considered, give benefits, drawbacks, and why it was not chosen. Include retaining the current approach when relevant.]

## Consequences

[Record expected benefits, accepted costs, obligations, risks, and limitations.]

## Confidence and reevaluation

[State confidence and its basis, unresolved assumptions, and observable changes that should trigger reevaluation through a new ADR.]

## Advice gathered

[When advice was gathered, summarize its source, influence, and unresolved disagreement. Link to the full discussion.]

## Supporting material

[Link to evidence, related ADRs, and detailed designs as needed.]
```
