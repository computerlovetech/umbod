---
type: Testing Guide
title: Mutation testing feedback
description: Use surviving mutations to strengthen behavioral tests without crossing public boundaries.
---

# Mutation testing feedback

## Outcome and boundary

Find meaningful faults the tests fail to detect, then protect the required behavior through the narrowest supported public interface. Mutation score is a diagnostic, not the goal or proof of correctness.

Never import, expose, patch, or inspect production-private methods or variables just to kill a mutant. Keep the behavior real and fake only external boundaries. If a useful behavior cannot be reached cleanly, propose the smallest production refactor and wait for approval; do not broaden the test into unrelated application setup.

## On-demand use

Use this guide directly while writing or strengthening tests; invoking the manual `improve-testability` skill is not required. Proactively consider mutation feedback for important error paths, weak assertions and coverage-preserving rewrites, without requiring it for every edit.

Keep mutation testing out of CI and release pipelines. It is a focused test-design tool, not a scheduled check, mandatory test stage or mutation-score gate.

Python tooling is available as the pinned `mutmut` development dependency in `umbod/api`. Run it through `uv` from that directory, with an isolated analysis copy when needed to protect unrelated working-tree changes. Select source, tests and worker limits explicitly for each task rather than installing a repository-wide mutation run by default.

## Bounded loop

1. **Establish trust.** Record the source/test scope, tool version, configuration, and passing baseline. Use deterministic tests and bounded workers. Verify the mutated code is actually imported and a known behavior-changing mutation produces a relevant failure.
2. **Inspect findings.** Review a bounded batch of survivors and their associated tests. Classify each as a meaningful gap, unclear requirement, equivalent mutation, noncontractual detail, or execution/selection problem. Keep no-test findings, timeouts, crashes, and incomplete results separate from assertion effectiveness.
3. **Give actionable feedback.** Send the test-writing agent the source location, mutation, tests executed, suspected missing behavior, and expected observable outcome. Ask it to protect the contract or explain the disposition—not to kill every mutant.
4. **Improve the test.** Strengthen observable result, state, side-effect, or required-interaction assertions. Group related mutations into one behavioral gap. Explain new regression cases and report the case-count delta. Escalate missing public seams rather than introducing private access.
5. **Prove the improvement.** The test must pass on the original code and fail meaningfully with the mutation active. Explicitly rerun affected mutants after test edits; use a fresh scoped run for final confirmation. Run ordinary required verification too. For rewrites, investigate lost kills using the same source and analysis scope before and after.
6. **Close the batch.** Report behaviors newly protected, accepted survivors with reasons, unresolved refactor recommendations, and execution/review cost. Stop at the agreed scope; do not claim whole-suite adequacy.

## Python: mutmut

- Keep a compatible release pinned alongside test dependencies. Mutmut 3 requires fork support; use a compatible local environment or a disposable Linux environment and validate plugin compatibility.
- Configure explicit source and test selection. Start with at most two mutation workers and serial pytest execution. Check sandbox imports against editable installations and pytest path settings. Avoid nested pytest-xdist workers.
- For programmatic CLI launchers, change to the analysis directory before importing mutmut; configuration is loaded during import. Verify the effective configuration so a scoped run cannot silently become full-suite collection.
- Inspect results with `mutmut results`, `mutmut show`, and `mutmut tests-for-mutant`; rerun reported mutant names explicitly. Do not use `mutmut apply` in a working tree containing unrelated changes.
- Cached verdicts are not fresh verification. Regenerate the sandbox when associations or configuration change. A successful run exit can still contain survivors; inspect results and completeness.
- Mutmut 3 focuses on functions, so retain ordinary coverage and other checks. Do not add exclusions, private assertions, or count timeouts as successful behavioral detection to improve a score.

## References

- [Mutmut documentation](https://mutmut.readthedocs.io/en/latest/) — Check configuration and commands against the pinned release.
- [Mutation testing at Google](https://testing.googleblog.com/2021/04/mutation-testing.html) — Prioritize actionable findings over exhaustive mutant counts.
