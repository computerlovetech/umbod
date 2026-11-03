# Telemetry ingestion

Umbod receives agent telemetry using OTLP/HTTP JSON or binary protobuf. This receiver is independent of Umbod's Prometheus metrics and administrator authentication.

## Endpoints

| Method | Path | OTLP request |
| --- | --- | --- |
| POST | /v1/logs | ExportLogsServiceRequest |
| POST | /v1/metrics | ExportMetricsServiceRequest |
| POST | /v1/traces | ExportTraceServiceRequest |

Requests use `application/json` or `application/x-protobuf`; media types are case-insensitive and optional parameters are accepted. Uncompressed and gzip bodies are supported for both encodings, with the same wire and decompressed size limits. Binary protobuf uses the signal-specific OTLP export request schema. gRPC is not supported.

These routes exist only on the collector listener, default port 4318. Public REST excludes all `/v1/*` ingestion routes, and `/api/v1/*` is not rewritten to them. The Helm chart exposes the collector through a private ClusterIP Service when `telemetry.enabled=true`, never through public Ingress. Direct collector Service access and port-forwards use the same `/v1/*` paths. Development Compose forwards container port 4318 only on `127.0.0.1:14318`.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| UMBOD_OTLP_ENABLED | false | Enable ingestion |
| UMBOD_OTLP_HOST | 0.0.0.0 | Collector listener interface |
| UMBOD_OTLP_PORT | 4318 | Collector listener port |
| UMBOD_OTLP_BEARER_TOKEN | Unset | Dedicated ingestion credential |
| UMBOD_OTLP_ALLOW_UNAUTHENTICATED | false | Explicit local-profile development access |
| UMBOD_OTLP_MAX_REQUEST_BYTES | 10485760 | Maximum wire and decompressed body size |

An enabled authenticated receiver requires a nonblank token without whitespace. Send it using the `Authorization` bearer scheme. Administrator and MCP credentials are not substitutes. Store the token in a deployment Secret; Helm injects the dedicated `telemetry.bearerTokenSecret` key only into API. Do not override chart-managed receiver settings through container environment values. Connections exposed beyond a trusted local boundary must use HTTPS.

Unauthenticated access is forbidden outside the local profile. With ingestion disabled, the API host does not start the collector listener. A separately composed disabled receiver returns 503. Configuration inspection excludes the bearer token.

The bind address selects network interfaces, not authorization. Restrict collector reachability separately and retain bearer authentication. Private Tailscale access requires separately configured Serve and ACLs, not public Funnel; Umbod does not configure Tailscale.

## Serving applications

`umbod api serve` delegates to `umbod.hosting.api_server.run_api_server`. One serving process and asynchronous event loop run public REST and, only when `UMBOD_OTLP_ENABLED=true`, the private collector. The public application never mounts ingestion routes. The host creates and readies one analytics runtime shared by administrator reads and collector writes, then closes it only after both listener lifespans drain.

`umbod.hosting.listeners` supervises the primary HTTP listeners. The parent enters each ASGI lifespan and forwards its yielded state to requests. Readiness requires every enabled primary listener to start successfully; startup failure or an unexpected listener exit stops its siblings. The existing embedded Prometheus listener remains separate and does not install signal handlers; the host owns shutdown signals. Cooperative listener cleanup and analytics shutdown have deadlines. The CLI also arms a 60-second process shutdown deadline on a stop request or host failure; if cancellation-resistant work prevents exit, it terminates the serving process with status 1.

`umbod api serve --reload` uses Uvicorn's ChangeReload watcher around the same serving child. The development watcher adds a process, but both HTTP ports still belong to one child PID. If the child fails, the watcher waits for the next edit according to standard reloader behavior.

`umbod telemetry serve` serves the collector-only FastAPI app in an independent Uvicorn process. `--host`, `--port`, and `--reload` control that process; host and port otherwise use the collector settings above. The command loads only runtime, receiver, and analytics settings. Production collection needs its dedicated ingestion token, not REST OIDC configuration, connector storage, or the application root secret.

The collector app exposes `/health` and `/ready` alongside `/v1/*`, but no administrator or connector routes. The supported `umbod.hosting.create_telemetry_app` factory accepts `TelemetryAppConfig` and can be mounted under an ASGI parent. The parent must explicitly enter the child's lifespan because ASGI mounts do not run child startup and shutdown automatically. Hosts own logging configuration; INFO telemetry output must remain enabled.

Mounting an ASGI app does not create another listener. The API host instead binds two distinct applications to separate listeners. Independently embedding the factory remains supported, with explicit parent lifespan ownership.

Standalone collection owns its analytics database lifecycle. Administrator queries remain on REST and are not remotely forwarded to a collector. Independently deployed hosts do not automatically share collected history: use collector-local durable storage, not SQLite over network storage.

## Helm collector deployment

The chart's `telemetry.enabled` value enables the private collector listener as an additional port on the existing API container and creates a ClusterIP Service targeting the same core Pod. `telemetry.port` controls the listener; `telemetry.servicePort` controls the Service port. Both default to 4318. There is no separate collector Deployment, image, resource allocation, or PVC, and no public `/v1` Ingress route.

Set `telemetry.bearerTokenSecret.name` to an existing Secret containing the ingestion credential. `telemetry.bearerTokenSecret.key` defaults to `UMBOD_OTLP_BEARER_TOKEN`. Only the API container receives this dedicated Secret key; MCP does not. Enabling telemetry enables authenticated ingestion, not analytics.

Configure the shared analytics runtime through `config.telemetryAnalytics.enabled` and `config.telemetryAnalytics.sqlitePath`. Analytics is disabled by default and uses a separate SQLite file on the core data volume. Core `persistence` settings govern durability. Accepted logs stored by this listener are available to the same API's administrator queries. The retired `telemetry.image`, `telemetry.analytics`, and `telemetry.persistence` settings are not supported.

## Serialization dependencies

The API project's reusable `telemetry-serialization` dependency group contains `opentelemetry-proto`, `protobuf`, and `googleapis-common-protos`. The API group includes it; standalone packaging can select it without the API or MCP dependency groups. The monolithic wheel retains these runtime requirements. No gRPC runtime, exporter SDK, or protobuf compiler is required by the receiver.

## Client compatibility

Claude Code requires telemetry enabled, the desired OTLP exporter selectors, and the explicit `http/json` protocol. Its shared HTTP endpoint is the base URL preceding `/v1`; signal-specific endpoints must contain their full signal paths.

Codex configures logs, metrics, and traces independently. Select its HTTP exporter with the `json` protocol and supply a complete endpoint URL for each signal. A configured Codex endpoint is not automatically suffixed.

Both clients can attach the dedicated ingestion credential through exporter headers. Their signal activation, event attributes, and privacy options vary by version.

HTTP/protobuf exporters, including Hermes monitoring, can use the same signal endpoints with the `http/protobuf` protocol and the dedicated bearer credential in exporter headers. Protocol compatibility does not establish that a client emits session or tool events; the analytics dimensions still depend on its exported fields.

## Stdout behavior

Each nonempty accepted batch produces one INFO entry through the existing `umbod.structured` logger. Its attributes contain `event.name=umbod.telemetry.export`, `telemetry.signal`, and the parsed source export under `telemetry.payload`.

The outer timestamp and resource identify Umbod's ingestion entry. Source resources, scopes, timestamps, metric temporality, identities, and typed attributes remain nested in the payload. Payloads are not flattened, aggregated, or silently truncated. JSON exports preserve the source JSON payload. Protobuf exports are converted to OTLP JSON with hexadecimal trace/span IDs, integer enums, decimal-string 64-bit integers and base64 ordinary byte values. Unknown OTLP fields are ignored during validation; source JSON may retain them, while unknown binary fields are not represented in the converted payload.

With analytics disabled, nonempty exports are acknowledged after the existing stdout handler writes and flushes the entry. Disabled INFO logging, handler filtering, or an observable stdout write failure returns 503 rather than silently acknowledging suppressed telemetry. This does not guarantee durable delivery or successful downstream log collection. Retries may produce duplicates.

Empty valid exports succeed without a payload entry. The whole batch is validated before invoking the sink; no partial acceptance is performed.

## Responses

Successful exports return 200 with an empty signal-specific OTLP response in the request encoding: `{}` for JSON, or a zero-byte protobuf message with `application/x-protobuf`. An empty binary request is a valid empty export. Errors return `google.rpc.Status` in the same encoding, including authentication failures before parsing, with canonical status codes and safe messages without payloads or credentials. Unsupported or missing request media types use JSON error responses.

| Status | Meaning |
| --- | --- |
| 400 | Invalid JSON, protobuf, OTLP fields, or gzip data |
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

The administrator subapplication creates request-local readers from the API host's analytics runtime. Logs received on the private collector listener use that same runtime. REST does not connect its reader to independently deployed collectors.

### SQLite analytics configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| UMBOD_TELEMETRY_ANALYTICS_ENABLED | false | Enable the independent SQLite analytics backend |
| UMBOD_TELEMETRY_ANALYTICS_SQLITE_PATH | .data/analytics.sqlite3 | Analytics-only SQLite file |

The analytics path is independent of `UMBOD_DATA_DIR` and `UMBOD_CONNECTOR_STORE_SQLITE_PATH`. Development Compose enables analytics by default and explicitly defaults the path to `/app/data/analytics.sqlite3`; an explicit analytics opt-out remains supported. Ingestion remains separately opt-in through the forwarded OTLP settings. Helm maps `config.telemetryAnalytics.enabled` and `config.telemetryAnalytics.sqlitePath` to the API container, defaulting to disabled and `/app/data/analytics.sqlite3`. The chart requires the typed path to stay beneath `/app/data`; `persistence.enabled` controls whether the shared data volume survives Pod replacement. Analytics uses a separate database file on that volume, not a separate PVC. See [analytics backend configuration](../operations/configuration.md#analytics-backend). Persistent deployments must mount the selected location. Application database paths and their SQLite sidecars cannot be reused, including existing symlink and hardlink aliases. Analytics schema preparation rejects databases that are not recognized as analytics storage rather than adding analytics tables to them.

The API host owns shared analytics startup and shutdown independently of application persistence, closing it after both listener lifespans drain. The standalone telemetry app owns its own analytics startup and shutdown. With analytics enabled, a successful nonempty log export requires both the existing stdout delivery and the normalized SQLite batch transaction to succeed. A SQLite failure returns 503. These two destinations are not one atomic transaction: stdout may already contain a failed export, and client retries may duplicate records. Analytics writes are append-only; retention and deduplication are not implemented.

### Normalized log fields

Analytics stores occurrence time, trusted ownership state and the five supported dimensions, not log bodies or arbitrary attributes. Occurrence time uses `timeUnixNano`, then `observedTimeUnixNano`, then the server receipt time. Integer nanoseconds are reduced to integer microseconds without floating-point conversion.

Source comes from resource `service.name`. Event name uses the log `eventName`, falling back to string attribute `event.name`. Severity uses `severityText`; numeric-only severities remain missing. Session uses the first present string attribute among `session.id`, `session_id`, `conversation.id`, `conversation_id` and `mcp.session.id`. Tool uses `tool.name`, `tool_name` and `mcp.tool.name` in that order. Duplicate attribute keys use the last occurrence; nonstring values are missing. Empty string attributes remain distinct from missing fields.

All records received through the shared ingestion credential remain unowned. Client-provided identity attributes never populate trusted ownership. Owner-scoped queries therefore exclude these records until a trusted ownership mechanism is introduced.

## Sensitive data

Accepted payloads are logged without client-specific filtering. Authentication headers are never included. Exported payloads can contain personal information, prompts, tool arguments, outputs, and raw API content.

Keep client content-export options disabled unless explicitly approved. Configure log access controls, retention, and any required downstream filtering before enabling collection. Do not use telemetry as a complete transcript or an exactly-once audit stream.

## Verification

Unit and boundary tests cover all signals in JSON and protobuf, encoding-matched responses, authentication, schema validation, payload conversion, gzip, and request limits. The disposable Kind runtime runner enables the receiver with a generated test-only token, exercises all three signals, verifies their markers in API stdout, and queries seeded logs through the protected aggregate endpoint across grouping, filtering, missing/empty values and time buckets. Test credentials and receiver test values remain outside the published chart and application image.
