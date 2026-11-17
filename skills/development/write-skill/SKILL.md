---
name: write-skill
description: >
  Author concise skills with a fixed structure and deterministic validation. Use when creating or rewriting a SKILL.md file or checking template compliance.
---

# Write skill

## Outcome

A focused skill follows the template and passes structure and character-limit checks.

## Inputs

- Required: Capability, task triggers, destination, and observable acceptance conditions.
- Optional: Supporting references, deterministic operations, and a character budget.
- Default: Limit the entire SKILL.md to 3,000 characters, including frontmatter, whitespace, and newlines; exclude supporting files.

## Rules

- R1: Use SKILL.md and a lowercase, hyphenated verb-noun name matching its directory; edit sources under skills/, not installed copies.
- R2: Preserve template structure and item counts; replace placeholders. Keep any disable-model-invocation: true field after the folded description and retain explicit invocation gates.
- R3: Move detail to references/, templates to references/templates/, and operations to scripts/. Reference real resources; use '- None required.' for standalone skills.

## Workflow

1. Establish capability, inputs, triggers, and acceptance conditions; inspect authoring and distribution conventions.
2. Read references/templates/SKILL.md and author the destination SKILL.md with the same structure, concrete defaults, and recovery actions.
3. Add necessary supporting files; review actions, triggers, and observable completion conditions.
4. Run python3 scripts/validate_skill.py /absolute/path/to/SKILL.md (or a skill directory tree); inspect every PASS/FAIL and repair failures using its guidance. Use --max-chars only for an agreed override.

## Decisions

| Condition | Action |
|---|---|
| Required input is missing | Ask for the missing capability, destination, or acceptance condition. |
| An optional input is missing | Apply the 3,000-character budget; include only necessary supporting resources. |
| Validation fails | Fix structure or move detail to supporting files, then rerun. |
| Recovery fails | Stop and report errors; never claim completion or silently raise the budget. |

## Output

Return:
- The authored SKILL.md and supporting file paths.
- Check result and character count against the agreed budget.
- Unresolved limitations requiring human review.

## Completion criteria

- The structure check exits successfully within budget; every referenced resource exists.
- Instructions define triggers, actions, recovery, and observable completion without placeholders; validation does not prove semantic quality.

## References

- Read `references/templates/SKILL.md` when authoring; it is a project template, not an external standard.
- Run `scripts/validate_skill.py` to report independent checks with repair guidance; --format json emits structured reports. Directory scans exclude references/, scripts/, and tests/. Exit 0 means success, 1 failure, 2 invalid arguments.
