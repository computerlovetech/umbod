# Telemetry ingestion

Enable telemetry only if agents need to send logs, metrics, or traces to Umbod. Before turning it on, restrict collector access, provision an ingestion credential, and decide who can read the exported data and how long to keep it. Use the private collector, not the public REST API. The collector accepts OTLP/HTTP JSON or binary protobuf and is separate from Umbod's Prometheus metrics and administrator sign-in.

## Sensitive data

Before enabling collection, configure log access controls, retention, and any required downstream filtering. Leave client content-export options off unless explicitly approved. Exported payloads may contain personal information, prompts, tool arguments, outputs, and raw API content. Umbod logs accepted payloads without client-specific filtering, but does not include authentication headers. Do not rely on this as a complete transcript or an exactly-once audit stream.

## Helm collector deployment

Check `helm show values` for your chart version before using the settings below. Chart `0.0.1-beta.9` has no `telemetry.*` values or separate collector Service. On that release, ingestion uses the API Service: set `UMBOD_OTLP_ENABLED=true` through `core.api.env` and supply `UMBOD_OTLP_BEARER_TOKEN` through `existingSecret`. The bundled Ingress routes `/v1` to the API. Leave ingestion off unless your deployment keeps that route private.

Point `telemetry.bearerTokenSecret` at an existing Secret containing the ingestion credential: set `telemetry.bearerTokenSecret.name` to the Secret name and use `telemetry.bearerTokenSecret.key` if the key is not `UMBOD_OTLP_BEARER_TOKEN` (the default). Only the API container receives this key; MCP does not.

Turn on `telemetry.enabled` by setting `telemetry.enabled=true`. This starts the private collector in the existing API container and creates a ClusterIP Service targeting the core Pod. Set `telemetry.port` for the listener and `telemetry.servicePort` for the Service; both default to 4318. There is no separate collector Deployment, image, resource allocation, or PVC, and no public `/v1` Ingress route.

If clients need setup discovery, set `telemetry.publicBaseUrl` to the collector base URL they can reach. It defaults to blank, maps to `UMBOD_OTLP_PUBLIC_BASE_URL` in API only, and does not add public ingress. Enabling ingestion does not enable analytics.

Configure the shared analytics runtime through `config.telemetryAnalytics.enabled` and `config.telemetryAnalytics.sqlitePath`. Analytics is disabled by default and uses a separate SQLite file on the core data volume. Core `persistence` settings govern durability. Accepted logs stored by this listener are available to the same API's administrator queries. The retired `telemetry.image`, `telemetry.analytics`, and `telemetry.persistence` settings are not supported.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| UMBOD_OTLP_ENABLED | false (true in development Compose) | Enable ingestion |
| UMBOD_OTLP_PUBLIC_BASE_URL | Empty | Advertised public collector base URL for authenticated setup discovery |
| UMBOD_OTLP_HOST | 0.0.0.0 | Collector listener interface |
| UMBOD_OTLP_PORT | 4318 | Collector listener port |
| UMBOD_OTLP_BEARER_TOKEN | Unset | Dedicated ingestion credential |
| UMBOD_OTLP_ALLOW_UNAUTHENTICATED | false | Explicit local-profile development access |
| UMBOD_OTLP_MAX_REQUEST_BYTES | 10485760 | Maximum wire and decompressed body size |

Set `UMBOD_OTLP_ENABLED` to `true` to enable the API-hosted collector outside Helm. For authenticated ingestion, provision a nonblank token without whitespace and store it in a deployment Secret. Clients send it using the `Authorization` bearer scheme. Administrator and MCP credentials are not substitutes. With Helm, use the chart settings rather than overriding chart-managed receiver settings through container environment values. Use HTTPS for connections exposed beyond a trusted local boundary.

Unauthenticated access is forbidden outside the local profile. With ingestion disabled, the API host does not start the collector listener. A separately composed disabled receiver returns 503. Configuration inspection excludes the bearer token.

Restrict who can reach the collector and keep bearer authentication enabled. The bind address only selects network interfaces. For private Tailscale access, configure Serve and ACLs, not public Funnel. Umbod does not configure Tailscale for you.

## Client compatibility

For Claude Code, enable telemetry, select the desired OTLP exporters, and set the protocol explicitly to `http/json`. Its shared HTTP endpoint is the base URL preceding `/v1`; signal-specific endpoints must contain their full signal paths.

For Codex, set up logs, metrics, and traces independently. Select its HTTP exporter with the `json` protocol and supply a complete endpoint URL for each signal. A configured Codex endpoint is not automatically suffixed.

Both clients can attach a personal telemetry token or the dedicated shared ingestion credential through exporter headers. Their signal activation, event attributes, and privacy options vary by version.

HTTP/protobuf exporters, including Hermes monitoring, can use the same signal endpoints with the `http/protobuf` protocol and the dedicated bearer credential in exporter headers. Protocol compatibility does not establish that a client emits session or tool events; the analytics dimensions still depend on its exported fields.

## Endpoints

| Method | Path | OTLP request |
| --- | --- | --- |
| POST | /v1/logs | ExportLogsServiceRequest |
| POST | /v1/metrics | ExportMetricsServiceRequest |
| POST | /v1/traces | ExportTraceServiceRequest |

Requests use `application/json` or `application/x-protobuf`; media types are case-insensitive and optional parameters are accepted. Uncompressed and gzip bodies are supported for both encodings, with the same wire and decompressed size limits. Binary protobuf uses the signal-specific OTLP export request schema. gRPC is not supported.

These routes exist only on the collector listener, default port 4318. Public REST excludes all `/v1/*` ingestion routes, and `/api/v1/*` is not rewritten to them. The Helm chart exposes the collector through a private ClusterIP Service when `telemetry.enabled=true`, never through public Ingress. Direct collector Service access and port-forwards use the same `/v1/*` paths. Development Compose forwards container port 4318 only on `127.0.0.1:14318`.

## Authenticated setup discovery

Set `UMBOD_OTLP_PUBLIC_BASE_URL` if you want signed-in users to discover the logs endpoint through `GET /api/me/telemetry/setup`. This endpoint uses the same eligibility rules as personal access token management, including its strict local-development gate. It does not require administrator access. All responses are `Cache-Control: no-store`.

When the receiver is enabled and `UMBOD_OTLP_PUBLIC_BASE_URL` is configured, the response contains only `status: available` and `logs_endpoint`. The backend normalizes trailing slashes, preserves any reverse-proxy path prefix, and appends `/v1/logs` exactly once during derivation. Clients use this full endpoint without appending a signal path.

A disabled receiver returns only `status: unavailable` and `reason: disabled`, even if a public URL is configured. An enabled receiver without a public URL returns only `status: unavailable` and `reason: not_configured`. Availability describes configuration, not reachability; discovery performs no external probe or token database read and exposes no credentials or token metadata.

The advertised base URL must be absolute HTTPS, or HTTP on `localhost`, IPv4 loopback, or `::1` only. Credentials, query strings, fragments, controls, whitespace, and malformed hosts or ports are rejected. Blank means unconfigured. The value is independent of listener host and port: Umbod never infers it from request origins, forwarded headers, API/MCP URLs, or bind addresses. Enabling ingestion without an advertised URL remains supported. Configure any proxy route separately; this setting does not expose a listener or change routing.

Token creation, expiry and revocation remain on the generic personal access token API; discovery does not issue or manage credentials.

## Personal telemetry tokens

Use a personal access token when logs should be attributed to a user on the API-hosted collector. The token must have audience `umbod:telemetry` and scope `telemetry:write`. It authorizes only ingestion on `/v1/logs`, `/v1/metrics`, and `/v1/traces`, not REST, administrator analytics, or MCP requests.

Authenticated users create and manage tokens through the general [personal access token API](./personal-access-tokens.md) at `/api/me/personal-access-tokens`. Creation explicitly requests the `telemetry` permission at level `write`; the server resolves that request to the audience and scope above. Management is not tied to the collector and lists or revokes all tokens owned by the caller. Production requires an upstream-verified user. Explicit local development additionally allows only the configured simulated subject with the exact `urn:umbod:local` issuer, under the full local/dev/simulation/development configuration gate described in the token API reference. That local user receives real tokens through the same endpoints and workspace controls; the collector validates them normally and revocation takes effect immediately. Other simulated, semantic, test and deployment identities cannot manage tokens. Collector verification separately rejects tokens owned by `urn:umbod:local` outside that full gate, even if application persistence is reused after switching to production. Custom embedding must supply application settings to the verifier installer; the full configuration gate controls local-namespace tokens without affecting genuinely verified-user tokens. The former telemetry-specific management route is removed.

Application persistence stores only token hashes and metadata. The API and collector share the exact application persistence runtime. Each personal-token export requires a fresh primary-key lookup, constant-time hash comparison, and expiry, scope, audience, and revocation checks. Invalid personal tokens never fall back to the configured shared bearer. Registry failures reject the export with 503. There is no cross-request authorization cache.

The legacy shared bearer and its required deployment configuration remain supported. The independent `umbod telemetry serve` process remains shared-bearer-only; custom embedding must explicitly install a verifier backed by the authoritative application persistence runtime to accept personal tokens. It must not create an independent token database. When authentication is required, a validated personal token establishes ownership for newly stored analytics logs.

## Serving applications

Run `umbod api serve` to serve public REST and, only when `UMBOD_OTLP_ENABLED=true`, the private collector. Both use one process and event loop under `umbod.hosting.api_server.run_api_server`. The public application never mounts ingestion routes. Token management and verification share the application's database runtime. The collector and administrator reads share a separate analytics runtime. Both stay open until the enabled listeners finish shutting down.

All enabled primary listeners must start before Umbod reports ready. If one fails to start or exits unexpectedly, the host stops the other. The host handles shutdown signals, not the separate embedded Prometheus listener. Listener cleanup and analytics shutdown have deadlines. On a stop request or host failure, the CLI allows up to 60 seconds for process shutdown, then terminates a stuck process with status 1.

`umbod.hosting.listeners` supervises the primary HTTP listeners. The parent manages each ASGI application's startup and shutdown and passes its lifespan state to requests.

`umbod api serve --reload` uses Uvicorn's ChangeReload watcher around the same serving child. The development watcher adds a process, but both HTTP ports still belong to one child PID. If the child fails, the watcher waits for the next edit according to standard reloader behavior.

Run `umbod telemetry serve` for a standalone collector with no REST API. It runs the collector-only FastAPI app in its own Uvicorn process. Set `--host`, `--port`, or `--reload` as needed; host and port otherwise use the collector settings above. The command loads only runtime, receiver, and analytics settings. For production, supply the dedicated ingestion token; you do not need REST OIDC configuration, connector storage, or the application root secret.

The collector app exposes `/health` and `/ready` alongside `/v1/*`, but no administrator or connector routes. The supported `umbod.hosting.create_telemetry_app` factory accepts `TelemetryAppConfig` and can be mounted under an ASGI parent. The parent must explicitly enter the child's lifespan because ASGI mounts do not run child startup and shutdown automatically. Hosts own logging configuration; INFO telemetry output must remain enabled.

Mounting an ASGI app does not create another listener. The API host instead binds two distinct applications to separate listeners. Independently embedding the factory remains supported, with explicit parent lifespan ownership.

Standalone collection owns its analytics database lifecycle. Administrator queries remain on REST and are not remotely forwarded to a collector. Independently deployed hosts do not automatically share collected history: use collector-local durable storage, not SQLite over network storage.

## Serialization dependencies

The API project's reusable `telemetry-serialization` dependency group contains `opentelemetry-proto`, `protobuf`, and `googleapis-common-protos`. The API group includes it; standalone packaging can select it without the API or MCP dependency groups. The monolithic wheel retains these runtime requirements. No gRPC runtime, exporter SDK, or protobuf compiler is required by the receiver.

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
| 503 | Disabled receiver, unavailable token registry, suppressed logging, or observable stdout failure |

Limits are enforced while reading, including when Content-Length is missing. Large batches must be reduced at the exporter rather than truncated by Umbod.

## Analytical reads

Enable analytics if administrators need to query stored logs in the [log analytics explorer](../using-umbod/log-analytics.md). Metrics and traces still go only to stdout. Umbod cannot backfill from historical stdout.

The separate `umbod.core.telemetry.analytics` module defines asynchronous, backend-neutral readers and normalized log writers. The SQLite analytics driver in `umbod.infrastructure.telemetry` persists normalized `/v1/logs` records and executes counts, filters, grouping and time buckets inside SQLite.

Queries require an explicit instance or owner scope, a half-open UTC time range, exact-match dimension filters, ordered grouping, explicit time bucketing, and explicit offset pagination. Owner scopes contain trusted server-established owner IDs, not client-reported emails or resource attributes. Callers must authorize and construct scopes before invoking a reader. The current shared ingestion token does not establish these owners.

Ungrouped, unbucketed queries return one count, including zero. Grouped or bucketed queries return observed groups only, ordered by bucket and then dimension values with missing values first. Missing dimension values are explicit states, not empty strings. Pagination applies to completed aggregate rows, after scope, time and dimension filters and aggregation. Page boundaries never split an aggregate count. Backend unavailability must be reported as an error, not zero activity.

Concrete drivers, query compilation, schema preparation and connections live under `umbod/infrastructure/telemetry/`. Core contracts contain no SQL, paths, backend selectors or driver imports. Analytics deliberately uses its own database file, schema, readiness and lifecycle, completely separate from the application `PersistenceRuntime`, application database and application migrations. This separation implements the explicit analytics storage requirement; it does not change application persistence ownership.

### Administrator query endpoint

`POST /api/admin/telemetry/log-counts` returns typed count rows through the configured analytics reader. It requires administrator authentication, not the ingestion credential. Instance scope is constructed by the server; requests cannot supply a scope or choose owners. Cookie-bearing browser requests require the trusted Origin and `X-Umbod-Web-Request: 1` protections used by other administrator operations.

All request fields are required: `time_range` with aware `start` and `end`, `filters` with dimension and string values, ordered `group_by`, `bucketing` with kind `none` or kind `fixed` and minute/hour/day width, and `pagination` with required strict integer `limit` from 1 to 1,000 and `offset` from 0 to 9,007,199,254,740,991. Booleans, numeric strings and fractional values are rejected. Filters and grouping dimensions must be unique; each filter has a nonempty array of unique string values, including an empty string when explicitly selected. Supported dimensions are `source`, `event_name`, `severity`, `session_id`, `tool_name`, `activity_kind` and `outcome`.

Responses contain `rows` with `groups`, `count` and `bucket`, plus `has_more` indicating whether another aggregate row follows the page. No query-wide totals are returned. Each group identifies its dimension and an explicit missing or present string value. Buckets identify either no bucketing or their UTC start. Successful, validation and known backend-error responses are not cacheable. Invalid queries return 422; disabled or unavailable analytics returns 503 without backend diagnostics or partial counts. Administrator authentication and authorization failures retain 401/403 behavior.

Keep the time range, filters, grouping and bucketing fixed during traversal, advancing `offset` by the number of rows returned until `has_more` is false. Reads are live, not a snapshot: late ingestion can change counts or insert earlier-sorting rows even within a fixed time range, causing repeated or skipped rows between pages. An offset at or beyond the end returns empty `rows` and `has_more: false`. The ungrouped, unbucketed zero-count row appears only at offset zero.

### Personal query endpoint

`POST /api/me/telemetry/log-counts` accepts the same query fields and returns the same aggregate response as the administrator endpoint. It requires a signed-in user, not an ingestion token. The server scopes the query to that user's verified issuer and subject; requests cannot select another owner or broaden the scope. Counts exclude historical unowned logs and exports sent with the shared credential. Cookie-bearing requests require the trusted Origin and `X-Umbod-Web-Request: 1`.

Both REST subapplications create request-local readers from the API host's analytics runtime. Logs received on the private collector listener use that same runtime. REST does not connect its reader to independently deployed collectors.

### SQLite analytics configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| UMBOD_TELEMETRY_ANALYTICS_ENABLED | false | Enable the independent SQLite analytics backend |
| UMBOD_TELEMETRY_ANALYTICS_SQLITE_PATH | .data/analytics.sqlite3 | Analytics-only SQLite file |
| UMBOD_TELEMETRY_ANALYTICS_RAW_ARCHIVE_ENABLED | false | Save original OTLP log batches alongside normalized analytics; requires analytics enabled |
| UMBOD_TELEMETRY_ANALYTICS_RAW_ARCHIVE_RETENTION_DAYS | 30 | Positive number of days to retain raw batches, measured from server receipt |

The analytics path is independent of `UMBOD_DATA_DIR` and `UMBOD_CONNECTOR_STORE_SQLITE_PATH`. Development Compose enables analytics by default and explicitly defaults the path to `/app/data/analytics.sqlite3`; an explicit analytics opt-out remains supported. Ingestion remains separately opt-in through the forwarded OTLP settings. Helm maps `config.telemetryAnalytics.enabled` and `config.telemetryAnalytics.sqlitePath` to the API container, defaulting to disabled and `/app/data/analytics.sqlite3`. The chart requires the typed path to stay beneath `/app/data`; `persistence.enabled` controls whether the shared data volume survives Pod replacement. Analytics uses a separate database file on that volume, not a separate PVC. See [analytics backend configuration](../operations/configuration.md#analytics-backend). Persistent deployments must mount the selected location. Application database paths and their SQLite sidecars cannot be reused, including existing symlink and hardlink aliases. Analytics schema preparation rejects databases that are not recognized as analytics storage rather than adding analytics tables to them.

The API host owns shared analytics startup and shutdown independently of application persistence, closing it after both listener lifespans drain. The standalone telemetry app owns its own analytics startup and shutdown. With analytics enabled, a successful nonempty log export requires both the existing stdout delivery and the normalized SQLite batch transaction to succeed. A SQLite failure returns 503. These two destinations are not one atomic transaction: stdout may already contain a failed export, and client retries may duplicate records. Normalized analytics have no automatic retention or ingest deduplication.

### Raw log archive

Decide who can access raw logs and how long to keep them before enabling capture. The archive can contain private data analytics deliberately omits, such as prompts, file paths, and skill names. Restrict access to the analytics database, sidecar files, and backups to trusted services and operators; Umbod does not set separate archive permissions. The default Compose volume is shared by API and MCP. Use a dedicated API-only analytics mount if that is too broad.

Development Docker Compose enables raw capture by default when analytics is enabled. Set `UMBOD_TELEMETRY_ANALYTICS_RAW_ARCHIVE_ENABLED=false` to opt out. Outside development Compose, capture remains opt-in: set `UMBOD_TELEMETRY_ANALYTICS_RAW_ARCHIVE_ENABLED=true`, or on Helm set it in `core.api.env` and enable `config.telemetryAnalytics.enabled`. When capture is enabled, the SQLite transaction writes the validated, decompressed request bytes for each nonempty `/v1/logs` export together with its normalized rows. Umbod records the encoding, receipt time, authentication-established ownership, and the source position of each row. Metrics, traces, rejected exports, and historical analytics rows are not archived. A failed SQLite transaction saves neither the raw batch nor its normalized rows.

Analytics queries do not return raw data. Expiry removes archived batches without changing counts, but does not erase backups, old SQLite pages, or stdout copies. Turning off capture does not disable cleanup while the analytics runtime is active.

### Backfill retained logs

Preview the retained batches before applying a backfill. Run `umbod telemetry backfill` with either `--batch-id` or both `--from` and `--to`. The time window selects by server receipt time, includes its start, excludes its end, and requires timestamps with explicit offsets. If the selection exceeds the command’s batch limit, narrow the window or adjust `--limit`; the command never silently skips the excess. The command uses the server's configured analytics database and retention policy. Run it with access to that database and its SQLite sidecar files.

Preview opens the database read-only and leaves its contents unchanged. SQLite can still need to open or create WAL sidecar files, so run preview with the API active or allow SQLite to create those files in the database directory. Add `--apply` to replace normalized records using the normalizer in the installed Umbod version. The command preserves original receipt time and ownership, never migrates or purges the database, and reports only batch metadata and counts. Each batch commits independently; on failure the command stops and reports how many batches completed. Repeating an apply does not add duplicate rows or resubmit the batch to stdout.

Backfill cannot recover expired payloads, import older stdout exports, or add fields the installed normalizer does not retain. There is no HTTP replay endpoint.

### Normalized log fields

Analytics stores occurrence time, trusted ownership state, the seven supported dimensions and a versioned, allowlisted normalization record, not log bodies or arbitrary attributes. Occurrence time uses `timeUnixNano`, then `observedTimeUnixNano`, then the server receipt time. Integer nanoseconds are reduced to integer microseconds without floating-point conversion.

Source comes from resource `service.name`. Event name uses the log `eventName`, falling back to string attribute `event.name`. Severity uses `severityText`; numeric-only severities remain missing. Session uses the first present string attribute among `session.id`, `session_id`, `conversation.id`, `conversation_id` and `mcp.session.id`. Tool uses `tool.name`, `tool_name` and `mcp.tool.name` in that order. Duplicate attribute keys use the last occurrence; nonstring values are missing. Empty string attributes remain distinct from missing fields.

New logs authenticated with a valid personal ingestion token are attributed to its verified owner. Shared-credential exports, unauthenticated development exports, and historical records without an owner remain unowned. Client-provided identity attributes never establish ownership.

### Normalized activity fields

Producers can declare activity using the OTLP log-record string attribute `umbod.activity.kind`. Its exact accepted values are `tool_call`, `file_read`, `file_edit` and `skill_activation`; case changes, whitespace and nonstring values are invalid. A valid declaration takes precedence over the legacy mapping below, regardless of source, harness, event name, tool name or external-tool provenance. Explicit file kinds therefore also support external tools. Invalid, missing or wrong-typed declarations fall back to conservative producer mapping and ignore `umbod.activity.outcome`.

For the three tool kinds, `umbod.activity.outcome` accepts only exact strings `success`, `failure` and `unknown`. If this attribute is absent, the explicit `success` attribute supplies the legacy boolean or exact-string `true`/`false` fallback. If canonical outcome is present but invalid or wrong-typed, outcome is `unknown`, even when `success` is valid. Severity never determines outcome. Duplicate keys use the last occurrence, including invalid values. `skill_activation` never receives an outcome.

Declarations are producer claims, not Umbod-verified execution or success. Original source, event, tool, session and severity dimensions remain unchanged. Every input remains one stored analytics record, including unclassified records. Only approved dimensions and finite normalization evidence are retained, not arbitrary attributes, bodies, arguments, paths or skill identity. Declarations introduce no new dimensions or query API fields.

Without a valid declaration, classification first tries the semantic string record attribute `event.name` across tool-result, permission-decision and skill-activation variants. If that attribute is unrecognized, it tries the record `eventName`. When both candidates are recognized but conflict, the semantic attribute wins. Raw `event_name` display and filtering remain unchanged: the log `eventName` takes precedence over the attribute, even when it is generic source-location metadata. No source-location or line-number aliases are inferred.

The legacy mapping enriches only these recognized events:

| Producer event | Activity kind | File-tool classification |
| --- | --- | --- |
| `claude_code.tool_result` | `tool_call` | Exact `Read` becomes `file_read`; `Edit` and `Write` become `file_edit` |
| `claude_code.skill_activated` | `skill_activation` | None |
| `codex.tool_result` | `tool_call` | Native `apply_patch` becomes `file_edit`; shell execution is not classified |
| `codex.skill_invocation` | `skill_activation` | None |

Qualified event names identify the supported format even when `service.name` is customized. Claude's bare `tool_result` and `skill_activated` attributes are recognized only for sources `claude-code` and `claude-code-desktop`. The existing `codex` source with bare `tool_result` is retained as a legacy convention; it is not the current namespaced Codex producer contract. Bare names from other sources are not classified.

Legacy-mapped completed tools receive `outcome` of `success`, `failure` or `unknown` from the explicit `success` attribute. OTLP boolean values and exact strings `true` and `false` are supported. Missing or malformed values remain `unknown`; INFO, WARNING and ERROR severity do not determine execution outcome. Permission decisions, API requests and skill-file reads do not become completed tools or skill activations by inference.

Each input record produces one analytics record. File activity kinds are tool-call subtypes, so the Tool calls report filters all three tool kinds without duplicating records. File reports count calls, not distinct files. Skill reports count activation records, not distinct skills or successful task completions. Arguments, file paths and skill names are not retained for these reports.

The version-2 analytics schema adds the two nullable dimensions. Existing recognized records are classified from their retained source, event and tool fields during the transactional version-1 upgrade. Historical Codex `apply_patch` records remain generic `tool_call` records because native versus external tool provenance was not retained. Historical tool outcomes become `unknown` because their result attributes were not stored. Unrecognized history remains unchanged; the migration does not import historical stdout or recover discarded attributes.

Existing diagnostic/source-location events, including `codex_exec` events such as `event otel/src/events/session_telemetry.rs:375`, provider or metrics locations, and synthetic UI-check logs are not activity merely because of their source or tool names. Existing unclassified history cannot reliably be backfilled: discarded producer attributes, including semantic `event.name` values overridden by record metadata in the stored raw event dimension, cannot be reconstructed from retained dimensions. This contract does not reinterpret stored logs or modify the existing migration.

Legacy mappings follow [Claude Code monitoring](https://code.claude.com/docs/en/monitoring-usage), the [Codex tool-result producer](https://github.com/openai/codex/blob/main/codex-rs/otel/src/tool_result.rs), the [Codex skill-invocation producer](https://github.com/openai/codex/blob/main/codex-rs/otel/src/skill_invocation.rs) and its [native patch-tool definition](https://github.com/openai/codex/blob/main/codex-rs/core/src/tools/handlers/apply_patch_spec.rs). These contracts describe supported formats, not proof that a deployed client version exports every event. Missing activity is not a measured zero, and retransmitted exports can inflate all counts.

### Unified normalization evidence

Ingestion and replay share the OTLP decoder; the core normalization mapper interprets producer evidence independently of analytics. Analytics derives its existing projection from the canonical record. Normalized schema version, evidence schema version and mapping version are tracked separately. The model retains both original record-event and semantic event identities; it does not replace the raw analytics event dimension with the selected semantic event.

The finite source allowlist includes resource `service.name` and `service.version`, log attribute `app.version`, instrumentation scope name/version and allowlisted resource/scope schema URLs, source severity text/number, and separate source, observed and receipt integer nanoseconds with effective-time provenance. Service version and application version are separate fields. Correlations retain session, conversation, MCP-session, turn, prompt, request and tool-call identifiers independently, including Claude `tool_use_id` and Codex `call_id`; native OTLP trace/span IDs remain separate. Arbitrary attribute `trace_id` and `span_id` are not native tracing evidence. Legacy session and tool alias precedence is unchanged.

Tool-result records retain reported outcome, tool aliases, categorical namespace and explicit-versus-assumed provenance. Nonempty MCP origin/server strings become boolean indicators; their names and URLs are discarded. Documented `duration_ms` is interpreted as nonnegative milliseconds. An unqualified `duration` has no verified unit and remains invalid rather than assuming one. A reported wrapper result does not prove subprocess or task completion. Valid generic declarations remain producer claims, never verified execution.

Permission decisions never imply execution or create tool activity dimensions. Claude qualified `claude_code.tool_decision` and source-gated bare `tool_decision` recognize exact `accept`/`reject`; unknown decisions stay unknown. Codex qualified `codex.tool_decision` recognizes only verified scalar decision categories, not arbitrary structured values. A recognized semantic permission event wins even when the raw event says tool-result; this intentionally corrects the former classifier corner case that could imply execution. Unrecognized semantic events can fall back to a recognized raw permission event. Valid explicit activity declarations retain their precedence and report disagreement with recognized event evidence.

Mapping metadata separates producer identity from declaration authority. It flags known service-versus-event producer conflicts, declaration-versus-event activity conflicts and conflicting recognized event identities. Recognized semantic identity wins; generic source-location metadata alone is not a conflict. Skill activation stores only recognized trigger categories, never skill names, plugin IDs or private inventories. Claude `invocation_trigger` values `user-slash`, `claude-proactive` and `nested-skill` map to explicit, implicit and nested activation. Codex uses `skill.invocation_type` with exact explicit/implicit values, not a generic trigger attribute. Finite source enums are retained for replay. Unmapped records remain stored with explicit unmapped status.

The schema-URL allowlist accepts the exact HTTPS `opentelemetry.io` host with a `/schemas/major.minor.patch` path and numeric version components. Other nonempty URLs become invalid markers, including credential-, query- and fragment-bearing URLs. This validates the namespace and shape without fetching the URL or claiming that its version exists. New textual metadata is bounded to 1,024 characters; oversized values are omitted with an explicit invalid marker, not truncated or rejected with a server error. Existing legacy dimension strings retain their previous acceptance behavior. Invalid types and unknown categorical values produce finite invalid/unknown states without retaining malformed values. Canonical evidence can be passed back into the pure mapper for deterministic replay of the known mappings; it is not an unrestricted source archive.

Analytics schema version 3 adds nullable `normalization_json` to the same analytics row and transaction. Existing version-2 rows receive no fabricated evidence or reclassification. The existing version-1 activity migration remains in the upgrade chain. Manually created records must explicitly select unavailable evidence with reason `legacy_or_unspecified`; no new storage engine, endpoint, report or ownership policy is introduced. Canonical normalization version 2 extends the evidence with model requests, response usage and producer-estimated costs. Version-1 normalized records remain readable and replay with their original mappings; they are not silently supplemented with metadata that was never retained. SQLite schema version 4 adds the raw archive and nullable source links without importing or changing the normalized values of existing rows.

The Codex boundary fixture is derived from the pinned [tool-result producer](https://github.com/openai/codex/blob/5f2ce5e02c56905cebcb5781ec198b676f32f27c/codex-rs/otel/src/tool_result.rs). Verified scalar permission categories come from the same commit's [decision event](https://github.com/openai/codex/blob/5f2ce5e02c56905cebcb5781ec198b676f32f27c/codex-rs/otel/src/events/session_telemetry.rs) and [opaque decision representation](https://github.com/openai/codex/blob/5f2ce5e02c56905cebcb5781ec198b676f32f27c/codex-rs/protocol/src/protocol.rs). Codex skill field names and enums follow the separately pinned [skill-invocation producer](https://github.com/openai/codex/blob/0a76a2520f45af68b7a5386688a9714af0a3ccd2/codex-rs/otel/src/skill_invocation.rs). These snapshots establish mapping evidence, not supported released client versions.

### Model requests, token usage and estimated cost

The log-only mapper distinguishes Claude API requests and terminal API errors, Codex HTTP and WebSocket requests, Codex response usage, stream diagnostics and turn-scoped estimates. Qualified event names are recognized independently of service names; bare Claude names require the recognized Claude service. A recognized semantic model event takes precedence over a conflicting raw tool-result identity. Valid explicit activity declarations retain their existing precedence. Model events do not add tool or file activity dimensions, so the existing activity reports and coverage contracts remain unchanged.

Claude `input_tokens` excludes cache reads and writes. Cache-inclusive input is derived only when input, cache-read and cache-creation counts are valid; a derived total also requires output. Missing or malformed fields are never treated as zero. The `cache_creation_5m_tokens` and `cache_creation_1h_tokens` fields, documented from Claude Code 2.1.300, are lifetime breakdowns, not extra input to add to aggregate cache creation. Their reported zeros can coexist with positive aggregate creation when the producer did not receive a breakdown. Claude API errors describe terminal failure after internal retries; their attempt field must not be interpreted as one emitted event per retry.

Codex `codex.sse_event` is response-usage evidence only for `event.kind=response.completed` with usage fields. Generic poll and failure records can have the same kind without usage. The producer also uses this emitter for WebSocket responses, so its name does not establish actual SSE transport. The misleading source field `tool_token_count` maps to reported total tokens, never tool-specific tokens. Cached input and cache writes are already part of reported input; reasoning is a subset of output. These subsets are not added again. Reported totals remain separate from consistency checks and are not replaced by recomputed values. Producer-default zeros do not establish that the upstream provider explicitly reported zero, and custom-provider accounting remains a producer claim.

Counts retain missing, invalid and reported-zero states. Native integer token values are preserved without a float conversion, including values above double-precision's exact-integer range. Booleans, negative, fractional, nonfinite and out-of-range counts are invalid evidence rather than zero. Reported counts are bounded to signed 64-bit integers; integral doubles must remain within their safe-integer range. Derived sums that exceed the supported range become invalid evidence without rejecting the log. Numeric representation and source-field identity remain available for deterministic replay. HTTP status describes transport response, not successful model inference; a request attempt, stream diagnostic or approval never establishes completed inference.

Claude `cost_usd` and `cost_usd_micros` are alternate representations of one producer estimate, not separate charges. A valid micro-USD representation is preferred for accounting, with the other representation retained for comparison; differences are not summed. The comparison distinguishes exact agreement, differences within one micro-USD of representation rounding, and larger mismatches. Decimal source values are bounded to 96 characters, magnitude `1e20` and 18 fractional places. Codex `usage.estimated_usd` belongs to `codex.turn_cost` and remains turn-scoped, including when `turn.interrupted` is true. Estimates retain USD units, scope and producer-estimate provenance using decimal arithmetic. They are not billed spend, independently verified pricing, or allocations to nearby requests.

Producer-reported `model` and Codex `slug` remain distinct claimed identifiers; neither proves the served model or provider. Identifier validation excludes paths, URLs, email addresses and account-bearing structured names. Server, client and authentication request IDs remain distinct correlations without establishing ownership. Raw errors, endpoints, headers, prompts, bodies and open-ended `query_source` attribution are excluded; error presence can survive without its content. No request/response stitching or deduplication is performed.

Usage mappings follow the [Claude API and accounting documentation](https://code.claude.com/docs/en/monitoring-usage) and the pinned Codex [event producers](https://github.com/openai/codex/blob/5f2ce5e02c56905cebcb5781ec198b676f32f27c/codex-rs/otel/src/events/session_telemetry.rs), [shared model metadata](https://github.com/openai/codex/blob/5f2ce5e02c56905cebcb5781ec198b676f32f27c/codex-rs/otel/src/events/shared.rs) and [response usage decoding](https://github.com/openai/codex/blob/5f2ce5e02c56905cebcb5781ec198b676f32f27c/codex-rs/codex-api/src/sse/responses.rs). Fixtures are contract-derived test data, not captured client exports or guarantees of released-client availability.

Metrics, traces and cumulative protocol token updates remain separate signals. They are not converted into extra usage observations or combined with request logs. Existing exports can be retransmitted, so normalized evidence does not provide exactly-once billing totals. This feature supplies retained normalized evidence, not a new token/cost aggregation API, pricing engine or billing report.

## Verification

Unit and boundary tests cover all signals in JSON and protobuf, encoding-matched responses, authentication, schema validation, payload conversion, gzip, and request limits. The disposable Kind runtime runner enables the receiver with a generated test-only token, exercises all three signals, verifies their markers in API stdout, and queries seeded logs through the protected aggregate endpoint across grouping, filtering, missing/empty values and time buckets. The local-development Kind stage creates, lists and revokes real personal telemetry tokens through REST and checks all three collector signals and immediate revocation. The verified-user Kind stage additionally creates personal telemetry tokens through REST, verifies all three signals, rejects those tokens on REST and MCP, and confirms that revocation through another API process immediately blocks collector access. Test credentials and receiver test values remain outside the published chart and application image.
