---
name: write-skill
description: >
  Author concise skills with a fixed structure and deterministic validation. Use when creating or rewriting a SKILL.md file or checking its template compliance.
---

# Write skill

## Outcome

A focused skill follows the supplied template and passes the structure and character-limit check.

## Inputs

- Required: The capability, task triggers, destination, and observable acceptance conditions.
- Optional: Supporting references, deterministic operations, and a character budget.
- Default: Use a 6,000-character budget for the entire UTF-8 SKILL.md, including frontmatter, whitespace, and newlines; supporting files are excluded.

## Rules

- R1: Name the entrypoint SKILL.md and use a lowercase, hyphenated verb-noun name matching its parent directory; edit repository sources under skills/, not installed copies.
- R2: Preserve the template's frontmatter, heading order, three input bullets, three numbered rules, four workflow steps, four decision rows, three output bullets, and two completion bullets; replace every placeholder with actionable content.
- R3: Keep instructions short, move supporting detail to references/, store templates in references/templates/, and only reference real supporting files; do not invent checks or claim validation proves semantic quality.

## Workflow

1. Establish the capability, required inputs, triggers, and acceptance conditions; inspect the destination's authoring and installation conventions.
2. Read references/templates/SKILL.md and use it to author the destination SKILL.md, preserving its structure and defining concrete defaults and recovery actions.
3. Add only necessary supporting references and deterministic scripts, then review the skill for clear actions, useful triggers, and observable completion conditions.
4. Run the named structure check with python3 scripts/validate_skill.py /absolute/path/to/SKILL.md from this skill directory; pass --max-chars only when a different budget was explicitly agreed, and repair all failures before rerunning.

## Decisions

| Condition | Action |
|---|---|
| Required input is missing | Ask for the specific capability, destination, or acceptance condition before authoring. |
| An optional input is missing | Apply the 6,000-character budget and include only supporting resources needed by the workflow. |
| Validation fails | Correct the reported structure or shorten SKILL.md by moving detail into supporting files, then rerun the same check. |
| Recovery fails | Stop the affected work and report the remaining errors without claiming completion or silently increasing the budget. |

## Output

Return:
- The authored SKILL.md and any supporting file paths.
- The structure-check result and character count against the agreed budget.
- Any unresolved limitations, including behavior that requires human review.

## Completion criteria

- The structure check exits successfully within the agreed character budget, and every referenced resource exists.
- The skill describes specific triggers, executable actions, recovery behavior, and observable acceptance conditions without unfilled placeholders.

## References

- Read `references/templates/SKILL.md` when creating or restructuring a skill; this is the supplied template, not an independently verified external standard.
- Run `scripts/validate_skill.py` to check UTF-8 input, filename, frontmatter, headings, section structure, placeholders, resource paths, and the character budget; it exits 0 on success and 1 on validation failure.
