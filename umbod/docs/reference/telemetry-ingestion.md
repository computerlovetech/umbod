# Telemetry ingestion

Umbod receives Claude Code and Codex telemetry using OTLP/HTTP JSON. This receiver is independent of Umbod's Prometheus metrics and administrator authentication.

## Endpoints

| Method | Path | OTLP request |
| --- | --- | --- |
| POST | /v1/logs | ExportLogsServiceRequest |
| POST | /v1/metrics | ExportMetricsServiceRequest |
| POST | /v1/traces | ExportTraceServiceRequest |

Requests use `application/json`, with optional charset parameters. Uncompressed and gzip bodies are supported. Protobuf and gRPC are not supported.

The Helm ingress routes `/v1` unchanged to the API Service. It does not rewrite `/api/v1` to these routes. API Service access and port-forwards use the same `/v1/*` paths.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| UMBOD_OTLP_ENABLED | false | Enable ingestion |
| UMBOD_OTLP_BEARER_TOKEN | Unset | Dedicated ingestion credential |
| UMBOD_OTLP_ALLOW_UNAUTHENTICATED | false | Explicit local-profile development access |
| UMBOD_OTLP_MAX_REQUEST_BYTES | 10485760 | Maximum wire and decompressed body size |

An enabled authenticated receiver requires a nonblank token without whitespace. Send it using the `Authorization` bearer scheme. Administrator and MCP credentials are not substitutes. Store the token in a deployment Secret; Helm supports existing Secret environment injection and API environment overrides. Public connections must use HTTPS.

Unauthenticated access is forbidden outside the local profile. Routes return 503 when disabled. Configuration inspection excludes the bearer token.

## Client compatibility

Claude Code requires telemetry enabled, the desired OTLP exporter selectors, and the explicit `http/json` protocol. Its shared HTTP endpoint is the base URL preceding `/v1`; signal-specific endpoints must contain their full signal paths.

Codex configures logs, metrics, and traces independently. Select its HTTP exporter with the `json` protocol and supply a complete endpoint URL for each signal. A configured Codex endpoint is not automatically suffixed.

Both clients can attach the dedicated ingestion credential through exporter headers. Their signal activation, event attributes, and privacy options vary by version.

## Stdout behavior

Each nonempty accepted batch produces one INFO entry through the existing `umbod.structured` logger. Its attributes contain `event.name=umbod.telemetry.export`, `telemetry.signal`, and the parsed source export under `telemetry.payload`.

The outer timestamp and resource identify Umbod's ingestion entry. Source resources, scopes, timestamps, metric temporality, identities, and typed attributes remain nested in the payload. Payloads are not flattened, aggregated, or silently truncated. Unknown OTLP message fields are ignored during schema validation; source payloads may retain them.

Nonempty exports are acknowledged after the existing stdout handler writes and flushes the entry. Disabled INFO logging, handler filtering, or an observable stdout write failure returns 503 rather than silently acknowledging suppressed telemetry. This does not guarantee durable delivery or successful downstream log collection. Retries may produce duplicates.

Empty valid exports succeed without a payload entry. The whole batch is validated before invoking the sink; no partial acceptance is performed.

## Responses

Successful exports return 200 with an empty JSON OTLP response. Errors return JSON canonical status codes and safe messages without payloads or credentials.

| Status | Meaning |
| --- | --- |
| 400 | Invalid JSON, OTLP fields, or gzip data |
| 401 | Missing or invalid ingestion credential |
| 413 | Wire or decompressed request limit exceeded |
| 415 | Unsupported media type or content encoding |
| 503 | Disabled receiver, suppressed logging, or observable stdout failure |

Limits are enforced while reading, including when Content-Length is missing. Large batches must be reduced at the exporter rather than truncated by Umbod.

## Sensitive data

Accepted payloads are logged without client-specific filtering. Authentication headers are never included. Exported payloads can contain personal information, prompts, tool arguments, outputs, and raw API content.

Keep client content-export options disabled unless explicitly approved. Configure log access controls, retention, and any required downstream filtering before enabling collection. Do not use telemetry as a complete transcript or an exactly-once audit stream.

## Verification

Unit and boundary tests cover all signals, authentication, JSON schemas, payload preservation, gzip, and request limits. The disposable Kind runtime runner enables the receiver with a generated test-only token, exercises all three signals, and verifies their markers in API stdout. Test credentials and receiver test values remain outside the published chart and application image.
