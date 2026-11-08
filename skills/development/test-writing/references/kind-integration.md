---
type: Test Practices
title: Kind integration test practices
description: Risk-driven live service tests for deployed authentication, persistence, lifecycle and cross-process behavior.
---

# Kind integration practices

Read [pytest practices](pytest.md) as well: the live tests are Python tests, but their integration boundary intentionally uses real services and persistence rather than in-memory substitutes.

## When to add a live test

- Add or extend a test when the behavior depends on deployment configuration, real authentication, service routing, shared persistence, process independence, startup or shutdown, or another boundary that in-process tests cannot establish.
- State the deployed failure the test should detect. A new route alone does not require duplicating every validation case in the live suite.
- Keep domain permutations, input validation and isolated error mapping in focused unit or in-process tests. Retain deployed security and wiring cases even when related unit coverage exists.
- Distinguish the decision to add coverage from the requirement to run the existing suite. Follow `AGENTS.md` for required verification.

## Reuse the existing runtime harness

- Use [the disposable Kind runner](../../../../umbod/tests/kind-runtime/run.sh) and its [test fixtures](../../../../umbod/tests/kind-runtime/README.md), rather than building another cluster runner inside a pytest test.
- Put live API and MCP tests in [the live runtime suite](../../../../umbod/api/live_runtime_tests/) and reuse its endpoint fixtures and readiness checks.
- Make new tests discoverable in the correct runner stage. Tests requiring verified sign-in credentials belong in the verified-user stage; an intentional skip in another stage is not evidence that the test passed.
- Keep connector fixtures, identity fixtures, SDK credentials and test-only deployment values under the test harness. Do not add them to published charts or application images.

## Exercise the claimed boundary

- Call real public interfaces using HTTP or the appropriate protocol client. Provision test resources through supported interfaces rather than bypassing the feature with direct database writes.
- Use genuinely verified credentials when testing authentication and ownership. A simulated development identity does not prove signature, issuer or audience enforcement.
- Establish that a protected route exists and works with an authorized caller before treating a denial as security evidence. A 404 from a missing route is not an authorization test.
- For cross-process claims, perform the operation through a distinct worker or service instance sharing the intended persistence. Repeating requests against the same process does not prove process independence.
- Keep positive and negative assertions tied to one observable contract. Check exact status codes and relevant response fields, not merely that a request did not throw.
- Use independent identities for ownership and isolation tests. Verify that rejection leaves the legitimate owner's operation intact when relevant.
- Test eventual behavior with bounded condition polling only when eventual consistency is part of the contract. Immediate revocation or acknowledged durable writes must not be weakened by retries that hide stale state.

## Own resources and diagnostics

- Use unique resource identities and isolated test state. Keep live tests serial unless the harness and every shared fixture support concurrency.
- Give network calls explicit timeouts and use readiness conditions rather than fixed sleeps.
- Register cleanup as resources are acquired, including failure paths. Revoke issued credentials and remove test resources without hiding the original test failure.
- Never log plaintext tokens, credentials, raw sensitive payloads or unsanitized diagnostics. Use the harness's existing secret-log checks and diagnostic filters.
- Let the runner own cluster creation, port-forwards, pod diagnostics and teardown. Preserve its safeguards against deleting unrelated clusters.

## Verification and reporting

Run `bash umbod/tests/kind-runtime/run.sh` from the repository root. If it fails, inspect the runner's pod diagnostics and report the failing assertions. Report passed and skipped counts separately, note missing coverage or environment blockers, and confirm cleanup. Do not describe a failed or skipped integration case as passing.
