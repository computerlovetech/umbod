---
name: write-module-readme
description: >
  Author module knowledge using Open Knowledge Format v0.2 and progressive disclosure. Use when creating, editing, or reviewing module READMEs or requested related knowledge Markdown.
---

# Write Module Knowledge

## Outcome

Module READMEs expose a progressive source index with valid OKF metadata and short relevance cues.

## Inputs

- Required: Target documents and sources; resolve their repository root before checks.
- Optional: Existing metadata, links, provenance, and explicit OKF bundle boundary.
- Default: Keep README.md as entrypoint with the minimal Software Module profile; do not convert the repository.

## Rules

- R1: Read the full guide before editing; preserve legitimate unfamiliar metadata and never invent provenance, dates, or human verification.
- R2: Module bodies contain only headings and linked bullets with relevance descriptions of at most 160 characters; use child README links for progressive disclosure.
- R3: Resolve links and symlinks; source READMEs stay within their source tree except repository ADRs. Never bulk-convert landing pages, ADRs, product docs, or skills.

## Workflow

1. Read references/guide.md fully before working; inspect sources and existing documentation for accurate relevance cues.
2. Use the module template, or index template for explicit bundle navigation; replace placeholders and ground optional metadata in evidence.
3. Preserve valid metadata, repair moved links, and remove empty headings, standalone explanations, source duplication, and forbidden body structures.
4. Run all four README scripts and skill tests with the guide's requirements and absolute target repository argument; fix findings and rerun.

## Decisions

| Condition | Action |
|---|---|
| Target root or scope is unclear | Infer from the request and workspace, not the skill installation; ask only if materially ambiguous. |
| Optional metadata or bundle boundary is absent | Omit unsupported metadata; keep the module README profile without declaring a bundle. |
| Validation fails | Fix YAML, structure, descriptions, links, or navigation findings and rerun every required check. |
| Recovery remains blocked | Stop and report exact findings and unverified checks; do not claim README completion. |

## Output

Return:
- Changed README or requested knowledge-document paths and their linked navigation updates.
- Outcomes of all four README checks and bundled skill tests.
- Unresolved findings and incomplete checks.

## Completion criteria

- Metadata, body restrictions, relevance cues, links, and progressive disclosure follow the full guide.
- All four scripts and skill tests exit successfully before README work is called complete.

## References

- Read `references/guide.md` when authoring module knowledge, before task work; it contains templates, OKF rules, and required commands.
- Run `scripts/check_readme_navigation.py` to validate navigation alongside all other guide checks.
