---
type: Operational Guide
title: Safe application diagnostics
description: Diagnostic field contracts, privacy boundaries, and investigation of application failures.
---

# Safe application diagnostics

Application diagnostics explain failures without copying the data being processed. Public error messages and internal diagnostic records are separate contracts. A generic client response does not justify a generic internal failure reason.

## Signal-owned side effects

[ADR-013: Signal-Owned Application Logging and Side Effects](https://github.com/computerlovetech/umbod/blob/main/umbod/project/architecture-records/ADR-013-signal-owned-application-logging.md) governs this standard and its exceptions.

Application operations publish typed failure events; logging, metrics, and audit adapters own the corresponding side effects. Reuse the existing application-local signal system rather than introducing a global event bus or invoking a logging helper inside an operation.

Capture and sanitize failure evidence at the failure point, before cleanup can replace it. Publish an immutable snapshot with approved context, not a live exception, traceback object, request, payload, or credential. Every receiver, not only the logging receiver, must receive safe data.

REST composition constructs a configured failure channel for its application and injects its publishing port into metrics middleware. MCP telemetry composition constructs its channel before the audit recorder and shares that publishing port with audit and OpenAPI lookup adapters. Logging is a named receiver registered during composition; application instances do not share subscriptions. Producers depend on the generic publishing port, not a logger or the full MCP signal collection.

Delivery uses the existing synchronous, receiver-isolating signals. These are transient diagnostic notifications, not durable messages or a new background queue. A failed receiver must not change the operation's result or prevent other receivers from running. Failures in ordinary MCP invocation or inventory receivers publish safe notifications to the separate application-failure channel, so other diagnostic receivers can observe them. Only the terminal failure handler of that diagnostic channel may log a sanitized failure directly; it must never republish through the failing channel. Bootstrap failures before channel construction need the same minimal nonrecursive fallback discipline.

Existing invocation completion signals continue to drive invocation logging, metrics, and audit. Intentional OTLP export remains an explicit data-delivery operation, not a best-effort side effect: export failures must still be reported to the caller.

## Required diagnostic context

Application failure events use fixed event descriptions and approved component, operation, outcome, and reason values. Event-specific fields must have a bounded, typed contract. Do not add arbitrary metadata dictionaries to a failure event.

The shared application-event contract uses `event.name=application.failure`, `component`, `operation`, `outcome=failure`, `reason`, and `failure.origin=internal`, plus sanitized exception evidence. REST metric failures retain an approved method, static normalized route, and public response status. Built-in signal receivers use allowlisted readable names; unknown receivers and connector-lookup identifiers use deterministic fingerprints rather than arbitrary input text. Audit-write failures preserve the original trace/span correlation without recursively retrying the failed audit sink.

MCP invocation completion records retain the existing connector, tool, operation, execution mode, duration, outcome, trace, and span attributes. Their failure contract includes:

| Field | Meaning |
| --- | --- |
| `mcp.failure.category` | Invocation failure classification. |
| `mcp.failure.origin` | Internal application, connector execution, downstream OpenAPI, or downstream MCP evidence. |
| `mcp.failure.stage` | Stage at which the operation failed. |
| `mcp.failure.reason` | Allowlisted, machine-readable diagnostic reason. |
| `mcp.downstream.response_received` | Whether this diagnostic carries downstream HTTP-response evidence. False does not prove the remote service was never contacted. |
| `mcp.downstream.http.status_code` | Downstream HTTP status, present only with response evidence; never Umbod's public response status. |
| `exception.type` | Captured exception type when an exception exists. |
| `exception.stacktrace` | Bounded frame locations and exception-chain types, without exception messages, source lines, or local variables. |

Response evidence belongs to the failing exchange. A successful initialization response must not supply a status for a subsequent failed connection. Existing diagnostic producers that do not capture HTTP-response evidence retain explicit absence rather than inventing a status. Returned failures need no fabricated traceback.

The diagnostic model is defined in [invocation diagnostics](https://github.com/computerlovetech/umbod/blob/main/umbod/api/src/umbod/core/invocation/diagnostics.py); the emitted MCP fields are defined by the [completion formatter](https://github.com/computerlovetech/umbod/blob/main/umbod/api/src/umbod/mcp/logging/invocation/formatting.py).

## Personal MCP transport reasons

| Reason | Interpretation |
| --- | --- |
| `http_rejected` | A non-success downstream HTTP status was rejected. |
| `authorization_rejected` | The downstream rejected authorization; existing authorization handling is preserved. |
| `content_encoding_rejected` | The response used an unsupported content encoding. |
| `charset_rejected` | The response declared an unsupported character set. |
| `invalid_content_length` | The response declared an invalid content length. |
| `response_size_exceeded` | A declared or streamed response exceeded the per-response limit. |
| `aggregate_size_exceeded` | Declared or streamed responses exceeded the operation-wide byte limit. |
| `request_size_exceeded` | The outgoing request exceeded its byte limit. |
| `protocol_rejected` | The bounded protocol or request guard rejected the exchange. |
| `network_failure` | A network operation failed. |
| `timeout` | The operation exhausted its time budget; a cleanup-only timeout uses runtime stage and internal origin, without a downstream status. |
| `target_expired` | The authorized runtime target expired. |
| `contract_mismatch` | The current tool contract did not match the approved call contract. |
| `runtime_failure` | An unexpected application/runtime failure occurred. Inspect sanitized exception evidence. |
| `transport_failure` | A producer supplied only the generic transport fallback. Treat this as a remaining instrumentation gap, not a root-cause diagnosis. |

The first meaningful failure must survive cancellation, task-group wrapping, session shutdown, and connection cleanup. Cleanup must not replace the primary reason, response evidence, or exception origin. A cleanup failure without an earlier operation failure must remain observable.

## Privacy rules

Never include credentials, tokens, authorization headers, OAuth codes or state, request/response bodies, tool arguments/results, personal data, or unrestricted endpoint URLs in application logs. Provider error descriptions are untrusted input: truncation does not make them safe. Map recognized provider codes to approved local reasons; use a fixed fallback for unknown codes.

Use normalized route identities rather than request paths or query strings. Existing approved connector and tool correlation is not permission to log arbitrary owner identities or private inventory metadata.

The [shared logging boundary](https://github.com/computerlovetech/umbod/blob/main/umbod/api/src/umbod/logging.py) sanitizes exception evidence and bounds primitive metadata. Unsupported objects must not be stringified. Metadata size bounds are resource controls, not secret redaction: an application-owned string still requires approval at its producer. Framework and dependency records must not bypass the application policy by embedding arbitrary text in messages or extra fields. Their free-form message text and extras are intentionally omitted; severity, logger identity, and sanitized exception evidence remain available. Application messages with interpolation arguments also use a fixed omission message. When more framework context is needed, add an explicit safe adapter/event rather than re-enabling arbitrary output.

Validated OTLP exports are a separate data-delivery contract, not application failure diagnostics. The stdout telemetry sink preserves those caller-supplied payloads through a dedicated typed export path; ordinary log metadata cannot bypass application limits by using a telemetry field name. Do not copy application secrets into telemetry exports. Destination access and retention policy still apply to accepted telemetry data.

Do not enable raw exception messages, HTTP debug bodies, or unsafe debug logging to investigate a generic fallback. Debug severity does not relax privacy rules. Ingress, reverse proxies, collectors, and external error reporters need their own credential and OAuth callback-query protections; application formatting cannot protect earlier logs. See [operator configuration](configuration.md).

## Investigating a failure

1. Select the invocation completion record and correlate by trace, connector, tool, and operation. Audit and invocation records describe different aspects of the same failure; their record counts are not independent incident counts.
2. Inspect origin, stage, reason, and downstream response evidence before interpreting HTTP status. Missing status must not be guessed from Umbod's public response.
3. For generic fallbacks, inspect sanitized exception types, frames, and nested causes. Identify the adapter branch that discarded a known condition, then reproduce it with a disposable scripted dependency.
4. Extend the allowlisted reason at that failure point and verify its propagation to serialized output. Do not broaden redaction exceptions or replay production writes to obtain more detail.
5. Preserve conservative uncertainty and no-replay behavior for OAuth exchanges and tool calls. More precise diagnostics do not establish whether an upstream mutation completed.

Expected denials and conflicts need explicit classification and an appropriate non-error severity. Genuine unexpected/internal failures must remain ERROR and alertable. Do not suppress all tool or filesystem errors to reduce alert volume.

## Verification and enforcement

Regression tests must exercise the real adapter through exception mapping to the final serialized record. Injected preclassified exceptions test formatting, but cannot establish that transport failures retain their original diagnostic detail.

Test both diagnostic usefulness and privacy: distinguish representative statuses, limits, encoding, timeouts, expiry, and cleanup failures; assert correlation and safe public responses; place sensitive sentinels in exceptions, payloads, credentials, and nested metadata and verify the complete emitted output excludes them. Signal tests must also inspect events with an independent subscriber, prove application-instance isolation and one configured log emission, and exercise receiver failure without recursive publication.

The shared [production design rules](https://github.com/computerlovetech/umbod/blob/main/.semgrep/production-design.yml) reject direct exception logging, explicit `exc_info`, and common dynamic-message interpolation in application source. The migrated failure producers additionally reject logging imports and direct logger calls; they must publish through the injected signal port. These syntax checks supplement typed event boundaries and output tests; they do not prove arbitrary data is safe. [Rule-contract tests](https://github.com/computerlovetech/umbod/blob/main/umbod/api/tests/test_semgrep_test_practices.py) verify behavior and source/test scope.

## Rollout scope

The implementation hardens shared exception formatting, routes metrics, connector-name lookup, and audit-write failures through application-local typed signals, retains a direct terminal signal-delivery failure fallback, restricts authentication and MCP debug records to approved categories, presence booleans and counts, and adds personal MCP transport diagnostics. OAuth provider failures, OpenAPI execution diagnostics, filesystem conflict classification, and storage-provider evidence require subsequent migrations to the same standard; they must not be described as fixed by the shared formatter alone.
