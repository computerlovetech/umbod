---
name: write-adr
description: >-
  Write a concise Architecture Decision Record with decision-first structure,
  context, alternatives, consequences, and a preserved decision history.
  Use only when explicitly invoked by the user.
disable-model-invocation: true
---

# Write an Architecture Decision Record

Follow this guide only when the user invokes this skill. Do not automatically invoke it during architecture work.

Based on Martin Fowler's [Architecture Decision Record](https://martinfowler.com/bliki/ArchitectureDecisionRecord.html). The template below adapts the article's guidance; it is not a verbatim template from the article.

## Purpose and writing style

- Capture one consequential decision relevant to a product or ecosystem, not an entire design or implementation plan.
- Explain why the decision made sense at the time so future readers can understand the system and its history.
- Use drafting to surface disagreements and clarify thinking, not merely to justify a predetermined choice.
- Follow an inverted pyramid: put the decision first, then the context and rationale, then supporting detail.
- Aim for one page, with a couple of pages as an upper bound. Link to research, diagrams, advice, and implementation detail instead of embedding them.
- Use plain, specific language. Name trade-offs and uncertainty rather than presenting the choice as universally correct.

## Workflow

1. Identify the decision, its scope, the problem, constraints, serious alternatives, and known consequences from the user's request and relevant evidence.
2. Read applicable repository instructions and existing ADRs. Check for related decisions, conflicts, and records that this decision would supersede.
3. Ask focused questions when the decision or essential rationale is missing. Do not invent research, alternatives considered, advice, owners, confidence, or team approval. Label unresolved facts explicitly.
4. Use the repository's existing ADR location and naming convention. In this repository, use `umbod/project/architecture-records/ADR-NNN-short-decision-title.md`. Choose the next number after the highest existing number; do not reuse gaps or renumber records. For another repository, discover its convention before creating a new location.
5. Draft using the template below. Default new records to Proposed unless acceptance is explicitly established. Preserve local metadata conventions while keeping the decision before explanatory detail.
6. List every serious alternative actually considered, including retaining the current approach when relevant. Record meaningful pros, cons, and the reason for not choosing each one.
7. Describe benefits, costs, risks, obligations, uncertainty, and concrete changes that should trigger reevaluation. Include a brief advice summary when advice was gathered, especially when using an Advice Process; link to the full discussion separately.
8. Check the record against the checklist, then report its path and any unresolved questions. Writing an ADR does not authorize implementing the decision.

## Status and history

- **Proposed:** Under discussion; the draft may evolve as evidence and advice arrive.
- **Accepted:** The team has accepted the decision and it governs the stated scope. Do not infer this status from existing code or from the request to write a record.
- **Superseded:** A later ADR significantly modifies or replaces the decision. Link to the replacement.
- Preserve accepted decisions and their original reasoning. Do not reopen or rewrite them to reflect a changed decision; create a new ADR instead.
- When a replacement is accepted, update only the old record's lifecycle metadata to mark it Superseded and link to the replacement. Link back from the new record and preserve the original decision text. Record the transition date so readers can trace when each decision governed the work.

## Template

Replace bracketed prompts with supported facts. Remove inapplicable optional metadata or sections; explicitly identify unknowns that matter to the decision. Repeat the alternative entry for each serious option considered.

```markdown
# ADR-[NNN]: [Short title that states the decision]

- **Status:** Proposed
- **Date:** [YYYY-MM-DD]
- **Decision owners:** [People or team responsible; if known]
- **Scope:** [Product, subsystem, or ecosystem boundary]
- **Supersedes:** [Relative link to earlier ADR; only when applicable]
- **Superseded by:** [Relative link to replacement ADR; only when superseded]
- **Status changed:** [YYYY-MM-DD; when a lifecycle transition occurs]

## Decision

[State what is chosen and where it applies in a few direct sentences. Make the decision understandable without reading the remaining sections.]

## Context and rationale

[Describe the problem, relevant facts, constraints, and competing forces. Explain why the chosen option best balances them in this context. Distinguish evidence from assumptions.]

## Alternatives considered

### [Alternative]

- Benefits: [Why this was a serious option.]
- Drawbacks: [Relevant costs and limitations.]
- Not chosen because: [Why it loses against the chosen option in this context.]

## Consequences

- Benefits: [Expected positive outcomes.]
- Costs and obligations: [Accepted trade-offs and follow-up responsibilities.]
- Risks: [Potential negative outcomes and remaining limitations.]

## Confidence and reevaluation

[State confidence and its basis, including unresolved assumptions. Name observable changes in context or evidence that should trigger reevaluation through a new ADR.]

## Advice gathered

[If applicable, summarize advice, its source, and how it influenced the decision. Note unresolved disagreement without implying consensus. Link to the full advice record.]

## Supporting material

[Link to relevant evidence, discussions, related ADRs, or detailed designs. Omit if unnecessary.]
```

## Completion checklist

- One decision, clearly stated near the beginning.
- Context and rationale explain why, not just what.
- Serious alternatives have fair pros, cons, and rejection reasons.
- Consequences cover downsides and obligations as well as benefits.
- Confidence, uncertainty, and reevaluation triggers are explicit.
- Advice and approval are represented accurately, without invented consensus.
- Status, scope, date, number, and any supersession links are consistent.
- Accepted history remains intact; supporting detail is linked rather than copied.
- The record is short enough to read in one sitting.
