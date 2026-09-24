---
name: atdd-implementation-loop
description: ATDD step 5. Implement production behavior in small slices until acceptance tests pass; refactor when green. Use after step 4 red run is documented.
disable-model-invocation: true
---

# ATDD Implementation Loop

## Use When
`04-acceptance-test-plan.md` exists with red run recorded.

## Inputs
- All four prior artifacts plus acceptance test command
- [references/executable-specifications.md](references/executable-specifications.md), [references/given-when-then.md](references/given-when-then.md) when preserving scenario intent
- If tests missing: use `atdd-write-acceptance-tests` first

## Do
- Plan small slices (Plan subagent); log to `05-implementation-loop.md`
- Implement one slice at a time; rerun acceptance tests after each slice
- Verify repository state and test results yourself — do not trust subagent summaries alone
- Refactor after green; use `choose-design-pattern` only for concrete smells
- Do not weaken, skip, or rewrite acceptance tests; no acceptance harnesses under production source dirs

## Write
`.atdd/features/<slug>/05-implementation-loop.md` — [assets/artifact-template.md](assets/artifact-template.md)

## Stop When
- Tests contradict approved scenarios or scope
- Passing would require weakening criteria or production-side test harnesses
- Three iterations with no reduction in failures
- Design decision needed outside clarified scope

## Done
- All mapped acceptance tests pass (or blockers with required earlier step)
- Plan, iterations, refactor pass, and final evidence recorded
- User gets summary of changed files, commands, and remaining risks
