---
name: svelte-docs-best-practices
description: >
  Apply official Svelte runes, events, composition, and rendering practices. Use when writing or reviewing Svelte 5 or SvelteKit components.
---

# Svelte docs best practices

## Outcome

Touched components follow official Svelte practices and repository placement rules.

## Inputs

- Required: Target components and intended behavior.
- Optional: Svelte version, configuration, and reactivity bug evidence.
- Default: Keep routes thin and reusable components in domain folders under src/lib/components/; async features are opt-in.

## Rules

- R1: Read the full guide before work; preserve its official documentation links, per-topic checks, and repository-specific placement rules.
- R2: Use justified state, raw state for suitable payloads, derived prop/computed values, attribute events, snippets, and stable unique each keys.
- R3: Treat effects as an escape hatch without mirror assignments or browser guards; preserve CSS-token, context/SSR, and legacy-migration rules.

## Workflow

1. Read references/guide.md; inspect target components and project configuration. Consult relevant official documentation when needed.
2. Apply the guide's runes, props, events, snippets, keyed-each, styling, context, and placement rules to touched code.
3. Load effect-usage-guard for deep effect review; check version and experimental.async before experimental features; use trace or explain why unnecessary for reactivity bugs.
4. Run the guide's per-topic verification and PR self-check; review legacy matches and document untouched exceptions.

## Decisions

| Condition | Action |
|---|---|
| Target or behavior is unclear | Inspect the request and workspace; ask only if material ambiguity remains. |
| Optional input is missing | Apply the stated default and inspect existing code. |
| Validation fails | Correct practice or configuration violations and repeat the relevant guide checks. |
| Recovery fails | Stop affected work and report the blocker; do not claim completion. |

## Output

Return:
- Changed component paths and applied practices.
- Per-topic and PR self-check results, including legacy exceptions.
- Unresolved limitations or blockers.

## Completion criteria

- Touched code satisfies the guide's runes, events, effect, keyed-each, composition, and placement checks.
- Context lifetime and experimental feature eligibility are verified where applicable.

## References

- Read `references/guide.md` when starting any task covered by this skill; reading the full guide before work is mandatory.
- Read `references/guide.md` when deep effect review requires effect-usage-guard or async use requires version, configuration, and team acceptance checks.
