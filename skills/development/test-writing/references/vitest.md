---
type: Test Practices
title: Vitest test practices
description: Focused frontend unit, reactive state and Svelte DOM tests with isolated state and explicit asynchronous behavior.
---

# Vitest practices

## Choose the boundary and location

- Keep tests beside the source module they verify. Name ordinary tests `*.test.ts` or `*.spec.ts` and Svelte DOM tests `*.dom.test.ts`.
- Check the owning package's test configuration before choosing an environment. Umbod's [Vitest configuration](../../../../umbod/frontend/vite.config.ts) separates ordinary unit tests from `happy-dom` tests.
- Test domain rules, state classes and application operations without mounting components when their public interfaces establish the behavior.
- Use DOM tests for rendered content, control eligibility, user interactions and component callbacks. Load the relevant Svelte skills when mounting or changing component behavior.
- Reserve real-browser checks for layout, browser-specific behavior, navigation and deployed application wiring. Do not treat `happy-dom` as proof of those behaviors.

## Assert observable behavior

- Use descriptive test names stating the condition and outcome. Keep each test focused on one behavior.
- Assert public results, state transitions, rendered content and collaborator outcomes rather than private fields or incidental implementation details.
- Assert that the intended control exists before interacting with it; optional chaining must not allow an interaction test to pass without acting.
- Check meaningful loading, empty, success, failure and authorization states where the feature has them.
- Use table-driven cases when the same setup and assertions apply to several meaningful inputs. Avoid unrelated Cartesian products and broad snapshots that obscure the contract.

## Isolate state and dependencies

- Create fresh mutable state, APIs and component instances for each test. Reuse existing typed in-memory implementations and focused test-support factories before creating new fakes.
- Inject external I/O collaborators for unit tests. Do not contact live APIs or start services to test frontend business rules.
- Test HTTP route adapters through their transport port, including response validation and error mapping. Keep business tests independent of fetch implementation details.
- Type helper parameters, return values and fake collaborators. Avoid `any` and unsafe casts that bypass the contract under test.
- Use focused mocks only where interaction assertions are the actual contract. Restore spies, globals and environment overrides after each test; clearing call history alone does not restore implementations.
- Own component unmounting, DOM removal, subscriptions and other cleanup through failure paths as well as successful tests.

## Handle asynchronous and reactive behavior

- Await promises and assertions; tests must not finish before their asynchronous work.
- Use Svelte's supported update synchronization, such as `tick` or `flushSync`, where needed after mounting or interacting. Do not introduce arbitrary sleeps or production effects solely for tests.
- Use controlled promises to test pending, completion and rejection states explicitly.
- Use fake timers only for behavior that depends on time. Advance them deliberately and restore real timers afterward.
- Verify that stale or cancelled work cannot overwrite current state when that is part of the public behavior.

## Verification

Use Bun in the frontend package. Run the focused Vitest tests while writing, then the applicable repository checks: from `umbod/frontend`, `bun run test` and `bun run check`. These practices do not replace the repository's real-browser verification requirements for UI changes.
