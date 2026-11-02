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

With analytics disabled, nonempty exports are acknowledged after the existing stdout handler writes and flushes the entry. Disabled INFO logging, handler filtering, or an observable stdout write failure returns 503 rather than silently acknowledging suppressed telemetry. This does not guarantee durable delivery or successful downstream log collection. Retries may produce duplicates.

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

## Analytical reads

The separate `umbod.core.telemetry.analytics` module defines asynchronous, backend-neutral readers and normalized log writers. The SQLite analytics driver in `umbod.infrastructure.telemetry` persists normalized `/v1/logs` records and executes counts, filters, grouping and time buckets inside SQLite. Metrics and traces continue to use stdout only. Administrators can use the [log analytics explorer](../using-umbod/log-analytics.md) for aggregate queries. Historical stdout backfill is not provided.

Queries require an explicit instance or owner scope, a half-open UTC time range, exact-match dimension filters, ordered grouping, explicit time bucketing, and a result-group limit. Owner scopes contain trusted server-established owner IDs, not client-reported emails or resource attributes. Callers must authorize and construct scopes before invoking a reader. The current shared ingestion token does not establish these owners.

Ungrouped, unbucketed queries return one count, including zero. Grouped or bucketed queries return observed groups only, ordered by bucket and then dimension values with missing values first. Missing dimension values are explicit states, not empty strings. Exceeding the group limit fails rather than silently truncating. Backend unavailability must be reported as an error, not zero activity.

Concrete drivers, query compilation, schema preparation and connections live under `umbod/infrastructure/telemetry/`. Core contracts contain no SQL, paths, backend selectors or driver imports. Analytics deliberately uses its own database file, schema, readiness and lifecycle, completely separate from the application `PersistenceRuntime`, application database and application migrations. This separation implements the explicit analytics storage requirement; it does not change application persistence ownership.

### Administrator query endpoint

`POST /api/admin/telemetry/log-counts` returns typed count rows through the configured analytics reader. It requires administrator authentication, not the ingestion credential. Instance scope is constructed by the server; requests cannot supply a scope or choose owners. Cookie-bearing browser requests require the trusted Origin and `X-Umbod-Web-Request: 1` protections used by other administrator operations.

All request fields are required: `time_range` with aware `start` and `end`, `filters` with dimension and string values, ordered `group_by`, `bucketing` with kind `none` or kind `fixed` and minute/hour/day width, and integer `max_groups` from 1 to 1,000. Filters and grouping dimensions must be unique; each filter has a nonempty array of unique string values, including an empty string when explicitly selected. Supported dimensions are `source`, `event_name`, `severity`, `session_id` and `tool_name`.

Responses contain `rows` with `groups`, `count` and `bucket`. Each group identifies its dimension and an explicit missing or present string value. Buckets identify either no bucketing or their UTC start. Successful, validation and known backend-error responses are not cacheable. Invalid queries and result-group overflow return 422; disabled or unavailable analytics returns 503 without backend diagnostics or partial counts. Administrator authentication and authorization failures retain 401/403 behavior.

The administrator subapplication creates request-local readers from the same independent analytics runtime that receives log writes; it does not open another runtime or use application persistence.

### SQLite analytics configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| UMBOD_TELEMETRY_ANALYTICS_ENABLED | false | Enable the independent SQLite analytics backend |
| UMBOD_TELEMETRY_ANALYTICS_SQLITE_PATH | .data/analytics.sqlite3 | Analytics-only SQLite file |

The analytics path is independent of `UMBOD_DATA_DIR` and `UMBOD_CONNECTOR_STORE_SQLITE_PATH`. Development Compose enables analytics by default and explicitly defaults the path to `/app/data/analytics.sqlite3`; an explicit analytics opt-out remains supported. Ingestion remains separately opt-in through the forwarded OTLP settings. Helm maps `config.telemetryAnalytics.enabled` and `config.telemetryAnalytics.sqlitePath` to the API container, defaulting to disabled and `/app/data/analytics.sqlite3`. The chart requires the typed path to stay beneath `/app/data`; `persistence.enabled` controls whether the shared data volume survives Pod replacement. Analytics uses a separate database file on that volume, not a separate PVC. See [analytics backend configuration](../operations/configuration.md#analytics-backend). Persistent deployments must mount the selected location. Application database paths and their SQLite sidecars cannot be reused, including existing symlink and hardlink aliases. Analytics schema preparation rejects databases that are not recognized as analytics storage rather than adding analytics tables to them.

REST owns analytics startup and shutdown independently of application persistence. With analytics enabled, a successful nonempty log export requires both the existing stdout delivery and the normalized SQLite batch transaction to succeed. A SQLite failure returns 503. These two destinations are not one atomic transaction: stdout may already contain a failed export, and client retries may duplicate records. Analytics writes are append-only; retention and deduplication are not implemented.

### Normalized log fields

Analytics stores occurrence time, trusted ownership state and the five supported dimensions, not log bodies or arbitrary attributes. Occurrence time uses `timeUnixNano`, then `observedTimeUnixNano`, then the server receipt time. Integer nanoseconds are reduced to integer microseconds without floating-point conversion.

Source comes from resource `service.name`. Event name uses the log `eventName`, falling back to string attribute `event.name`. Severity uses `severityText`; numeric-only severities remain missing. Session uses the first present string attribute among `session.id`, `session_id`, `conversation.id`, `conversation_id` and `mcp.session.id`. Tool uses `tool.name`, `tool_name` and `mcp.tool.name` in that order. Duplicate attribute keys use the last occurrence; nonstring values are missing. Empty string attributes remain distinct from missing fields.

All records received through the shared ingestion credential remain unowned. Client-provided identity attributes never populate trusted ownership. Owner-scoped queries therefore exclude these records until a trusted ownership mechanism is introduced.

## Sensitive data

Accepted payloads are logged without client-specific filtering. Authentication headers are never included. Exported payloads can contain personal information, prompts, tool arguments, outputs, and raw API content.

Keep client content-export options disabled unless explicitly approved. Configure log access controls, retention, and any required downstream filtering before enabling collection. Do not use telemetry as a complete transcript or an exactly-once audit stream.

## Verification

Unit and boundary tests cover all signals, authentication, JSON schemas, payload preservation, gzip, and request limits. The disposable Kind runtime runner enables the receiver with a generated test-only token, exercises all three signals, verifies their markers in API stdout, and queries seeded logs through the protected aggregate endpoint across grouping, filtering, missing/empty values and time buckets. Test credentials and receiver test values remain outside the published chart and application image.
