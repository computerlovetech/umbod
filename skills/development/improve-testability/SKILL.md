---
name: improve-testability
description: >-
  Manually review bounded batches of tests and their source code across languages,
  frameworks, and test suites. Remove implementation coupling through narrow public
  interfaces, preserve isolation, and recommend focused refactors when seams are missing.
disable-model-invocation: true
---

# Improve Testability

## Invocation and scope

- Run only when the user explicitly invokes this skill. Do not activate it automatically during ordinary development or test review.
- Determine the target source area and test suite from the user's request and current conversation. Do not assume a language, framework, repository layout, or test runner. Ask for scope only when the context does not identify it clearly.
- Default to one batch of three test files or equivalent suite units within that scope. Honor an explicitly requested scope or batch size. Include the source code needed to understand their responsibilities and dependency boundaries.
- Stop after the batch report. Continue with another batch only when requested.
- Test cleanup does not authorize production refactoring. Present recommendations and wait for explicit approval before changing production architecture or interfaces.

## Goal

Test observable behavior through the narrowest supported public interface without expanding the intended unit. Removing private calls is not sufficient if the replacement test exercises unrelated responsibilities or needs a large graph of implementation-sensitive mocks.

## 1. Establish the batch

1. Read repository instructions and applicable module READMEs. Identify the language, framework, test runner, package manager, and verification commands from the selected area. Load applicable testing, architecture, state-management, and lifecycle skills rather than assuming a particular stack. Read relevant accepted ADRs before proposing architectural changes.
2. Inspect working-tree changes. Preserve unrelated staged and unstaged work; do not stage, commit, or revert it.
3. Use the user's paths when supplied. Otherwise select three test files or equivalent suite units within the established scope that are not already covered in this routine, prioritizing concrete coupling rather than arbitrary files. Use previous reports to avoid duplicate batches. If fewer candidates remain, report that instead of silently expanding scope.
4. Inspect every test in each selected unit, including parameterized cases, fixtures, setup, teardown, and helpers. Read the corresponding source and composition boundaries. Search results are candidate discovery, not the review itself.
5. Record the selected test and source paths, current behavior under test, intended unit or component boundary, and focused baseline commands, results, and case counts.

## 2. Identify implementation coupling

Check for:

- Imports or direct calls to privately owned functions, methods, or classes.
- Patches, mocks, subclasses, or assignments that replace privately owned behavior or mutate internal state.
- Assertions on internal fields or construction details instead of required outcomes.
- Third-party private APIs and hidden framework/provider context dependencies.
- Dependencies created internally that prevent a focused fake from being supplied.
- Business rules, mutable state, derived state, or side effects owned by presentation or transport layers instead of the appropriate domain, application, or state unit.
- Tests that bypass public state transitions or only assert source text, markup shape, or construction details when runtime behavior is the intended contract.

Determine public ownership from documented contracts, exports, interfaces or protocols, framework conventions, and actual use, not naming or visibility syntax alone. An exported or non-underscored symbol can still be internal. Private helpers owned by the tests are not production-private violations by themselves.

For each finding, identify the behavior and code path currently protected, its public entry point, available dependency seams, and the isolation cost of switching entry points.

## 3. Choose the narrowest useful boundary

Prefer, in order:

1. The intended unit's public operation with existing explicit dependency injection.
2. Public dependency interfaces, protocols, or factories with small recording or in-memory fakes.
3. A focused component boundary when rendering, composition, state integration, or lifecycle orchestration is itself the intended behavior.
4. Existing application entry points when routing, authentication, protocols, startup, navigation, or end-to-end interaction is the subject of the test.

Do not route every test through a full application, browser, server, or lifecycle bootstrap. Distinguish a public source-level API from a public user or network entry point. Preserve unit tests as unit tests where possible; explicitly identify component, integration, or end-to-end tests when a broader boundary is justified.

A synchronous public dependency can also be a useful seam. Do not assume that simulating caller changes requires an asynchronous private hook.

## 4. Rewrite without weakening coverage

- Replace private imports, calls, and patches with public operations and injected dependencies where the isolation cost is reasonable.
- Do not merely rename or expose an internal helper, patch a different private method, or replace one private dependency with another.
- Keep the behavior being tested real. Fake external boundaries, not the rules, state transitions, rendering, or lifecycle behavior that the test claims to protect.
- Preserve success, error, denial, redaction, retry, cancellation, and cleanup assertions and all existing parametrized cases.
- Assert observable results, side effects, and required interactions. Do not replace a negative outcome assertion with only a constructor-call assertion.
- Keep fakes small, typed, and behavior-oriented. Avoid a parallel test framework or oversized fixture graph.
- Use bounded event or condition waits for asynchronous behavior. Do not replace deterministic checks with blind sleeps.
- Preserve resource ownership and cleanup. Avoid real external services in unit tests and disable unrelated background work, listeners, timers, or telemetry endpoints when testing lifecycles.
- Do not add or remove test cases merely to perform the cleanup. If regression coverage is necessary, explain it and report the exact case-count delta, including parametrization.
- Follow the selected source area's typing, naming, documentation, and code-style rules. Apply repository restrictions on comments and docstrings; do not introduce untyped helpers where the language and project require types.

## 5. Recognize a missing seam

If public coverage would require unrelated application state, rendering, authentication, persistence, networking, or service setup, retain the focused test rather than silently broadening it. Explain exactly which private dependency remains and why.

Recommend the smallest design change that removes the coupling:

- Internally constructed dependencies: explicit injection of a typed dependency, factory, or port at the owning unit's supported composition boundary.
- External I/O mixed into orchestration: ports and adapters with a test-owned in-memory implementation.
- Variable policy or algorithm: an injected strategy.
- Pure rules buried in orchestration: a cohesive domain operation with an explicit public contract.
- State or derived values mixed into presentation: the framework-appropriate state unit or class, with public transitions and read-only consumption by presentation where project conventions require it.

Use `choose-design-pattern` and read the selected pattern guidance when appropriate. Do not add an abstraction solely to satisfy a naming rule. Explain what remains real, what becomes replaceable, where production composition belongs, and who owns resource lifetimes.

## 6. Implement a refactor only after approval

When the user approves a recommendation:

1. Inspect every affected construction, initialization, composition, and lifecycle call site, existing interfaces or ports, and ownership contracts.
2. Define the public behavior and ownership boundary before its implementation. Reuse existing validated domain models. For external or replaceable dependencies, define the narrow typed interface first; do not invent dependency ports for pure rules or state extraction.
3. For dependency-boundary changes, prove the interface with a small recording or in-memory fake, then move external dependency construction into the appropriate production adapter, factory, or composition root. For pure rules or state extraction, test the extracted unit's public operations directly.
4. Require explicit injection where the consuming unit depends on replaceable collaborators. Wire concrete dependencies at the composition boundary, not through hidden default construction or a service locator.
5. Preserve operation and component lifetimes, capture timing, current authorization, telemetry, error classification, and disposal. Where relevant, retain reactive updates, derived-state correctness, navigation state, and cancellation semantics. Do not retain operation-owned resources or captured authority beyond their intended lifetime.
6. Replace the retained private patches with injected fakes. Add focused wiring, failure, cancellation, and cleanup regressions where warranted.
7. Update relevant module READMEs using `write-module-readme`; document genuine architecture changes through the applicable ADR process.

Do not fold unrelated defects or broad formatting into the refactor. Report additional risks separately.

## 7. Delegate and verify

- Prefer one bounded implementation subagent for the selected batch when delegation is available. Give it exact paths, behaviors to preserve, allowed edits, and verification responsibilities. Do not delegate an unbounded suite rewrite.
- Do not duplicate delegated searches or run concurrent full-suite tests. The parent reviews the actual diff and independently verifies the result before reporting completion.
- An independent review can check an approved production refactor for behavior, security, lifetime, and isolation regressions. Do not start large multi-agent workflows without explicit user authorization.
- Run focused tests before and after using the selected suite's supported file or case selection, from the correct working directory and with the repository-approved package manager. Prefer serial execution for small selections when supported; use the project's required concurrency limits otherwise.
- Follow current repository and area-specific verification requirements. Run the applicable broader suite, type checks, lint, static analysis, build checks, and diff checks for the changed area. Do not substitute one stack's checks for another's or run unrelated suites without a concrete dependency reason. Do not use uncapped workers or several concurrent full-suite runs.
- When runtime or interaction behavior changes, run the required environment-specific integration or browser checks. Verify actual postconditions such as state preservation, requests, output, and cleanup rather than relying on action dispatch alone. Use the mandated runtime and do not substitute a more convenient one. Inspect diagnostics and report failing assertions if a runner fails.
- Run required README checks when documentation changes and deployment checks when deployment artifacts change.
- Compare findings with the baseline without treating baseline findings as a clean scan. Follow repository remediation instructions; report unresolved findings or blocked checks explicitly. Never suppress findings just to obtain a passing result.
- Disclose an initial failure and any retry, including environmental failures. Do not attribute unrelated working-tree changes in full-suite counts to this batch.

## Final report

Provide a concise report containing:

- The established scope, selected test and source paths, and each intended unit or component boundary.
- Private dependencies removed, public replacements, and any dependencies deliberately retained.
- Whether tests remained isolated and which real behavior the fakes leave in place.
- Before/after focused case counts and reasons for additions or removals.
- Concrete refactor recommendations or approved refactors implemented; clearly distinguish recommendations from changes.
- Actual focused, full-suite, lint, static-analysis, documentation, and runtime outcomes as applicable, including skips, retries, unresolved findings, and checks not run.
- Confirmation that unrelated changes were preserved.

Do not claim the entire suite has been reviewed when only one batch was inspected.
