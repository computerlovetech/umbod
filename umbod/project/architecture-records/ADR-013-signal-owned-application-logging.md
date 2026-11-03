# ADR-013: Signal-Owned Application Logging and Side Effects

- **Status:** Accepted
- **Date:** 2026-11-02
- **Scope:** Shared backend application logging and optional observational side effects

## Decision

Application operations publish typed facts through the existing `umbod.core.signals` module. Registered receivers own logging and other optional observational side effects, including metrics and audit observation. Producers must not call loggers or logging helpers directly as a parallel application-level mechanism.

- Inject publishing ports and compose named receivers explicitly per application. No process-global event bus, hidden channel lookup, or implicit default channel inside a producer.
- Capture immutable, sanitized diagnostic snapshots at the failure point, before cleanup can replace the original evidence. Sanitize **before publication**, so every subscriber receives safe data. Preserve approved operation, reason, status, and correlation fields; never publish live exceptions, traceback objects, credentials, bodies, tool arguments/results, unrestricted URLs, or arbitrary metadata.
- Publish ordinary receiver failures to the separate application-failure channel. Only that channel's terminal failure handler may log directly without redispatch, avoiding recursion. Minimal bootstrap diagnostics before signals exist are also permitted. Low-level logging receivers and output adapters necessarily perform the actual writes; these are not an exception allowing operations to bypass signals.
- Do not replace primary I/O, acknowledged telemetry exports, transactional changes, or required durable writes with best-effort signals. Their failure and delivery guarantees remain explicit.

This extends the existing MCP invocation pattern to application-failure logging. It establishes the default for new and modified application-level observational behavior; it does not claim every legacy log site has already been migrated. It supplements, rather than supersedes, ADR-004 and ADR-008.

## Context and rationale

The investigation behind [issue #33](https://github.com/computerlovetech/umbod/issues/33) found lost diagnostic distinctions alongside code paths permitting raw exception content. This establishes a design inconsistency, not evidence of a production disclosure.

A shared safe logging helper improved output safety but left operations coupled to logging. MCP invocation signals already separated facts from logging, metrics, and audit receivers. Reusing that mechanism avoids a second application-level side-effect path and lets independent subscribers observe the same safe evidence.

Privacy must hold at the publishing boundary, not only in the JSON formatter. Otherwise a new subscriber could receive sensitive data that the logging receiver would have removed.

## Alternatives considered

- **Direct calls to a shared safe logging helper:** initially implemented; simple and centrally formatted, but couples operations to logging and prevents independent receivers from observing failures. Replaced with typed publication and a logging receiver.
- **Direct logging for every receiver failure:** initially retained as a recursion safeguard, but unnecessarily bypassed diagnostic subscribers for ordinary MCP receiver failures. Rejected where a separate failure channel is available; retained only for its terminal fallback and bootstrap diagnostics.

## Consequences

- Diagnostic contracts and side effects can be tested independently; adding a receiver does not require changing business operations.
- Composition must supply the publisher and register the intended receivers once, with application-instance isolation. This adds explicit wiring and event-contract maintenance.
- Delivery remains synchronous and receiver-isolating. Receivers add request-path work and must stay lightweight. In-memory signals provide no durable delivery or retry guarantee.
- Receiver failures must not change an operation's result or prevent remaining receivers from running. Terminal fallback must remain bounded and nonrecursive.
- Tests must inspect published events independently of logging, verify secret exclusion and immutable snapshots, preserve correlation, and cover receiver failure and duplicate emissions. Code review and the shared producer logging guards enforce the boundary; syntax checks alone cannot prove data safety.

## Confidence and reevaluation

The existing invocation pattern, signal-isolation regressions, serialized-output privacy tests, and disposable runtime verification support this decision. Performance at larger subscriber counts has not been established. Reevaluate through a new ADR if measured receiver latency, required delivery guarantees, or expanding fallback exceptions make this boundary unsuitable. Do not silently introduce direct application logging or a second event bus.

## Supporting material

- [ADR-004: One Backend API and a Thin Desktop Boundary](ADR-004-single-backend-api-and-desktop-boundary.md)
- [ADR-008: Event-Synchronized In-Memory Tool Runtime](ADR-008-event-synchronized-tool-runtime.md)
- [Signal module](../../api/src/umbod/core/signals/README.md) and [safe diagnostic publication](../../api/src/umbod/core/diagnostics/README.md)
- [Logging receiver and channel composition](../../api/src/umbod/logging.py)
- [Diagnostic field contract and investigation guide](../../docs/operations/application-diagnostics.md)
- [Signal and privacy regressions](../../api/tests/umbod/core/diagnostics/test_application_failure_signals.py) and [MCP receiver-failure regressions](../../api/tests/umbod/mcp/signals/test_application_failures.py)
- [Shared production design guards](../../../.semgrep/production-design.yml)
