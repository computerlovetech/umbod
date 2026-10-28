---
name: improve-testability
description: >-
  Manually review three API test modules at a time for private implementation
  coupling. Rewrite through narrow public interfaces, preserve isolation, and
  recommend dependency-injection refactors when a suitable public seam is missing.
disable-model-invocation: true
---

# Improve Testability

## Invocation and scope

- Run only when the user explicitly invokes this skill. Do not activate it automatically during ordinary development or test review.
- Default to one batch of three API test modules under `umbod/api/tests`. Honor an explicitly requested scope or batch size.
- Stop after the batch report. Continue with another batch only when requested.
- Test cleanup does not authorize production refactoring. Present recommendations and wait for explicit approval before changing production architecture or interfaces.

## Goal

Test observable behavior through the narrowest supported public interface without expanding the intended unit. Removing private calls is not sufficient if the replacement test exercises unrelated responsibilities or needs a large graph of implementation-sensitive mocks.

## 1. Establish the batch

1. Read repository instructions, applicable module READMEs, and the `python-test-practices` skill. Read relevant accepted ADRs before proposing architectural changes.
2. Inspect working-tree changes. Preserve unrelated staged and unstaged work; do not stage, commit, or revert it.
3. Use the user's module paths when supplied. Otherwise select three not already covered in this routine, prioritizing concrete private coupling rather than arbitrary files. Use previous reports to avoid duplicate batches. If fewer candidates remain, report that instead of silently expanding scope.
4. Inspect every test in each selected module, including parametrized cases, fixtures, and helpers. Search results are candidate discovery, not the review itself.
5. Record the selected paths, current behavior under test, intended unit, and focused baseline results and case counts.

## 2. Identify implementation coupling

Check for:

- Imports or direct calls to privately owned functions, methods, or classes.
- Monkeypatches, mocks, subclasses, or assignments that replace private methods or mutate private state.
- Assertions on internal fields or construction details instead of required outcomes.
- Third-party private APIs and hidden framework/provider context dependencies.
- Dependencies created internally that prevent a focused fake from being supplied.

Determine public ownership from documented contracts, module exports, protocols, and actual use, not underscores alone. A non-underscored symbol can still be internal. Private helpers owned by the tests are not production-private violations by themselves.

For each finding, identify the behavior and code path currently protected, its public entry point, available dependency seams, and the isolation cost of switching entry points.

## 3. Choose the narrowest useful boundary

Prefer, in order:

1. The intended unit's public operation with existing constructor-injected dependencies.
2. Public dependency protocols or factories with small recording or in-memory fakes.
3. A focused component boundary when composition or lifecycle orchestration is itself the intended behavior.
4. Existing HTTP or MCP entry points when routing, authentication, protocol behavior, or application startup is the subject of the test.

Do not route every test through `create_app()` or an application lifespan. Distinguish public Python APIs from public HTTP APIs. Preserve unit tests as unit tests where possible; explicitly identify component tests when a broader boundary is justified.

A synchronous public dependency can also be a useful seam. Do not assume that simulating caller changes requires an asynchronous private hook.

## 4. Rewrite without weakening coverage

- Replace private imports, calls, and patches with public operations and injected dependencies where the isolation cost is reasonable.
- Do not merely rename or expose an internal helper, patch a different private method, or replace one private dependency with another.
- Keep the behavior being tested real. Telemetry tests should run the real telemetry pipeline while faking outbound execution; caller-capture tests should retain actual capture and concurrency behavior.
- Preserve success, error, denial, redaction, retry, cancellation, and cleanup assertions and all existing parametrized cases.
- Assert observable results, side effects, and required interactions. Do not replace a negative outcome assertion with only a constructor-call assertion.
- Keep fakes small, typed, and behavior-oriented. Avoid a parallel test framework or oversized fixture graph.
- Use bounded event or condition waits for asynchronous behavior. Do not replace deterministic checks with blind sleeps.
- Preserve resource ownership and cleanup. Avoid real external services in unit tests and disable unrelated metrics listeners when testing app lifecycles.
- Do not add or remove test cases merely to perform the cleanup. If regression coverage is necessary, explain it and report the exact case-count delta, including parametrization.
- Follow repository code-style rules; add no code comments, docstrings, or untyped helpers.

## 5. Recognize a missing seam

If public coverage would require unrelated catalog, authentication, persistence, or networking setup, retain the focused test rather than silently broadening it. Explain exactly which private dependency remains and why.

Recommend the smallest design change that removes the coupling:

- Internally constructed services or clients: constructor injection of a typed factory or port.
- External I/O mixed into orchestration: ports and adapters with a test-owned in-memory implementation.
- Variable policy or algorithm: an injected strategy.
- Pure rules buried in orchestration: a cohesive domain operation with an explicit public contract.

Use `choose-design-pattern` and read the selected pattern guidance when appropriate. Do not add an abstraction solely to satisfy a naming rule. Explain what remains real, what becomes replaceable, where production composition belongs, and who owns resource lifetimes.

## 6. Implement a refactor only after approval

When the user approves a recommendation:

1. Inspect every constructor and composition call site, existing ports, and lifetime contracts.
2. Define the narrow typed interface before its implementation. Reuse existing validated domain models rather than introducing raw transport-shaped data into the core.
3. Prove the interface with an in-memory fake, then move existing construction into a production adapter or factory.
4. Require injection at the consuming unit. Wire concrete dependencies explicitly at the composition boundary, not through hidden default construction or a service locator.
5. Preserve fresh per-operation services, caller capture timing, current authorization, telemetry, exception classification, and resource disposal. Do not cache caller authority or operation-owned clients in a retained factory.
6. Replace the retained private patches with injected fakes. Add focused wiring, failure, cancellation, and cleanup regressions where warranted.
7. Update relevant module READMEs using `write-module-readme`; document genuine architecture changes through the applicable ADR process.

Do not fold unrelated defects or broad formatting into the refactor. Report additional risks separately.

## 7. Delegate and verify

- Prefer one bounded implementation subagent for the selected batch when delegation is available. Give it exact paths, behaviors to preserve, allowed edits, and verification responsibilities. Do not delegate an unbounded suite rewrite.
- Do not duplicate delegated searches or run concurrent full-suite tests. The parent reviews the actual diff and independently verifies the result before reporting completion.
- An independent review can check an approved production refactor for behavior, security, lifetime, and isolation regressions. Do not start large multi-agent workflows without explicit user authorization.
- Run focused tests serially before and after: use `uv run --locked pytest` with the selected module paths, `-q`, and `-n 0` from `umbod/api`.
- Follow current `AGENTS.md` verification requirements. Run the capped backend suite for the changed API tests or production code, plus Ruff, shared Semgrep, and diff checks. Do not use uncapped workers or several concurrent full-suite runs.
- For API or MCP application changes, run the required disposable Kind runtime tests; Docker Compose is not a substitute. Inspect diagnostics and report failing assertions if the runner fails.
- Run required README checks when documentation changes. Apply frontend or chart checks only if those areas changed.
- Compare findings with the baseline without treating baseline findings as a clean scan. Follow repository remediation instructions; report unresolved findings or blocked checks explicitly. Never suppress findings just to obtain a passing result.
- Disclose an initial failure and any retry, including environmental failures. Do not attribute unrelated working-tree changes in full-suite counts to this batch.

## Final report

Provide a concise report containing:

- Each of the three module paths and its intended unit or component boundary.
- Private dependencies removed, public replacements, and any dependencies deliberately retained.
- Whether tests remained isolated and which real behavior the fakes leave in place.
- Before/after focused case counts and reasons for additions or removals.
- Concrete refactor recommendations or approved refactors implemented; clearly distinguish recommendations from changes.
- Actual focused, full-suite, lint, static-analysis, documentation, and runtime outcomes as applicable, including skips, retries, unresolved findings, and checks not run.
- Confirmation that unrelated changes were preserved.

Do not claim the entire suite has been reviewed when only one batch was inspected.
