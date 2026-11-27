# Portable HTTP connectors

Apply the [portable connector reference](portable-connector.md) first. This SDK feature supports offline HTTP testing in CPython and Monty. It does not open sockets or supply a production runner. Live HTTPS, credential injection, and admin-managed bindings are not available for portable connectors yet.

## Targets and handler context

Declare `http_targets` as a dictionary from a logical target ID to a short description of its purpose, including whether it writes. IDs match `[a-z][a-z0-9_]{0,63}`; declare at most 16 targets with nonblank descriptions up to 256 characters. A target contains no URL, credential, or permission grant. A future Umbod broker will bind each target to an admin-approved HTTPS origin and base path and attach any approved credential. Connector configuration cannot grant access.

Use `HttpContext` from `umbod_sdk.connectors.http` as the injected `context` keyword in version 2 tools and configuration checks. Never place `context` or `configuration` in the public tool input schema. Use async handlers for HTTP and await the context methods. Choose a read-only call for configuration checks; do not use POST to test whether configuration is valid.

## Choose the request method

Every call takes the declared target ID, `path` as a list of decoded relative path segments, and `query` as a list of two-string lists. Query entries are ordered, and repeated keys are preserved. Use an empty list when no query is needed. Do not pass a URL, pre-escaped path, headers, or credentials.

| Awaitable method | Additional arguments | Result on success |
|---|---|---|
| `context.request` | `response_schema` | GET status and validated JSON when present |
| `context.request_status` | None | GET status only |
| `context.post` | `json_body`, `request_schema`, `response_schema` | POST status and validated JSON when present |
| `context.post_status` | `json_body`, `request_schema` | POST status only |

Use authoritative API contracts or redacted responses to choose schemas. The HTTP request and response schemas are nonempty JSON Schema Draft 2020-12 dictionaries, capped at 16 KiB each. Use in-document references only; `pattern` and `patternProperties` are unsupported. An upstream `response_schema` is separate from the tool's `output_schema`.

POST accepts structured JSON, not serialized strings containing JSON, raw bytes, or form/multipart data. A JSON string value is valid when its request schema permits a string. The boundary validates the body and limits its encoded UTF-8 size to 1 MiB before it reaches transport. POST is denied by default: the host must approve the exact target ID and relative path, with no implicit approval for sibling or descendant paths. GET access never grants POST access.

## Handle results without replaying writes

- A completed result contains `status` and a `body` tagged `json` (with `value`) or `no_content`. Status-only calls, no-content statuses, and 4xx/5xx responses never expose an upstream body. Redirects return `redirect_disallowed` and are not followed.
- A failure contains `error`. Request and response schema violations return `request_contract_mismatch` and `response_contract_mismatch` respectively, without leaking the payload. A missing POST approval returns `policy_denied` before transport is called.
- POST is never automatically retried. A transport failure or timeout returns `outcome_unknown`. Cancellation propagates. Neither cancellation nor a response error proves a write was rolled back; verify upstream state before deciding whether to repeat a write.

## Test with the real validation boundary and a fake transport

Use `HttpRequestBoundary` and `RawHttpResponse` from `umbod_sdk.connectors.api.http`. Inject a fake transport that implements async `send(request)` and records requests and returns raw status and body bytes. Pass the declared targets to the boundary; for positive POST tests set its host-only `approved_post_paths` to entries pairing a target ID with a tuple of exact path segments. In CPython, give the handler an `HttpContext` using the boundary's `dispatch`.

Assert what the fake recorded, including the POST JSON bytes in `HttpPostRequest.body`. Cover success, unknown or disallowed targets or paths, malformed or oversized request JSON, request and response schema mismatches, status-only body suppression, and timeout without replay. Invalid or denied requests must never reach the fake. Do not stub `HttpContext` to return already-decoded data: that bypasses the validation these tests are meant to exercise.

## Check Monty parity when needed

Monty is an optional test dependency, not part of the SDK runtime. In its test mount, create a lightweight `umbod_sdk` package: use an empty package initializer, the SDK's `connectors/declaration.py` as `connectors/__init__.py`, and `connectors/http.py` at its usual module path. Mount that package read-only; do not import the full CPython SDK inside Monty. On the host, enter an `async with` scope using `HttpInvocation` from `umbod_sdk.connectors.api.http_scope`. Expose `invocation.dispatch` through a Monty `ExternalModule`, then construct the sandbox's `HttpContext` with that async callback. Run the same connector and compare its manifest, result, and recorded requests with CPython. Use the invocation scope so cancellation also cancels its outstanding host request.
