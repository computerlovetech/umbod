# Telemetry collection

Enable collection only if agents need to send logs, metrics, or traces. Keep the collector private and require a dedicated bearer credential. Exports can contain prompts, tool data, and personal information; restrict access and set retention before enabling content export. Umbod does not redact accepted OTLP payloads for you.

## Helm collector deployment

Check for `telemetry.*` in `helm show values` for your chart. Chart `0.0.1-beta.9` lacks the private collector Service and routes ingestion through the API. Leave ingestion off on that release unless your deployment keeps `/v1/*` private.

1. Put the ingestion token in a Kubernetes Secret. Set `telemetry.bearerTokenSecret.name` and, if needed, `telemetry.bearerTokenSecret.key` (default `UMBOD_OTLP_BEARER_TOKEN`).
2. Set `telemetry.enabled=true`. The collector runs inside API and gets a private ClusterIP Service. `telemetry.port` and `telemetry.servicePort` default to `4318`. Do not route `/v1/*` through public Ingress.
3. For local tests, forward the collector Service. Development Compose publishes it at `http://localhost:14318` on loopback. Use HTTPS outside trusted local networks.

Outside Helm, set `UMBOD_OTLP_ENABLED=true` and a nonblank `UMBOD_OTLP_BEARER_TOKEN` for `umbod api serve`. A standalone `umbod telemetry serve` has independent analytics storage; its history does not appear automatically in API queries. Do not enable unauthenticated ingestion outside explicit local development.

## Configure a client

Send OTLP/HTTP POST requests to `/v1/logs`, `/v1/metrics`, or `/v1/traces` on the collector. It accepts JSON or protobuf, with optional gzip; gRPC is not supported. The default wire and decompressed size limit is 10 MiB. Send `Authorization: Bearer …` using the shared ingestion token or a [personal access token](personal-access-tokens.md) with telemetry write access. Shared-token exports are not attributed to a user. REST administrator and MCP credentials are not ingestion tokens.

Claude Code can use `http/json` and the base URL preceding `/v1`; signal-specific URLs must include their full path. In Codex, configure the HTTP `json` exporter separately for each signal with its full URL. See the [Codex plugin guide](../using-umbod/codex-plugin.md) for installer-based setup.

**Check:** Send one non-sensitive test log from the client and confirm HTTP 200. If analytics is enabled, look for the log in the explorer. For 401, check the ingestion token; for 413, reduce batch size; for 415, check content type and encoding. Successful earlier writes may not be rolled back by a later failure, so exporter retries can duplicate data.

## Authenticated setup discovery

Set `telemetry.publicBaseUrl` (`UMBOD_OTLP_PUBLIC_BASE_URL` outside Helm) for signed-in users to discover the logs endpoint via `GET /api/me/telemetry/setup`. Use the reachable HTTPS base URL (HTTP loopback is allowed), retain any proxy prefix, and omit `/v1/logs`: Umbod appends it. This setting neither enables the collector nor opens ingress. The setup response indicates configuration availability, not network reachability, and does not issue a token.

## Log storage and queries

Enable `config.telemetryAnalytics.enabled` separately to query normalized logs in the [log analytics explorer](../using-umbod/log-analytics.md). Set `config.telemetryAnalytics.sqlitePath` to a separate SQLite file under the persistent data mount (default `/app/data/analytics.sqlite3`). Do not reuse the application database or its sidecars. Metrics and traces go to stdout, not the log database. Umbod cannot backfill historical stdout.

`POST /api/admin/telemetry/log-counts` queries instance logs; `POST /api/me/telemetry/log-counts` reads only logs attributed to the signed-in user. Both use live, paginated aggregates. Refer to the deployed OpenAPI contract for request and response schemas.

### Raw log archive

Only enable raw archiving if operators need to reprocess retained OTLP log batches. Set `UMBOD_TELEMETRY_ANALYTICS_RAW_ARCHIVE_ENABLED=true` on API with analytics enabled; development Compose enables it by default. `UMBOD_TELEMETRY_ANALYTICS_RAW_ARCHIVE_RETENTION_DAYS` defaults to `30`. Restrict the database, sidecars, and backups: the raw archive can contain data omitted from analytics. Raw archive expiry does not remove normalized records, backups, or stdout copies.

Run `umbod telemetry backfill` against the configured analytics database with `--batch-id` or both `--from` and `--to` (timestamps with offsets) to preview retained batches. Add `--apply` to replace normalized rows in place using the installed normalizer. It cannot recover expired batches.

### Normalized activity fields

Producers can set `umbod.activity.kind` to `tool_call`, `file_read`, `file_edit`, or `skill_activation`. Tool kinds support `umbod.activity.outcome`: `success`, `failure`, or `unknown`. These are producer claims, not verified execution. Without a valid declaration, Umbod recognizes supported Claude Code and Codex tool-result and skill-activation events; it does not infer activity from generic logs or severity. Missing activity does not prove no work occurred. File reports count calls, not distinct files.
