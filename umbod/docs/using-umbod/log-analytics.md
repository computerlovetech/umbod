---
type: User Guide
title: Log analytics
description: Count ingested telemetry logs with administrator-owned filters, grouping and UTC time buckets.
---

# Log analytics

Administrators can open **Log analytics** in workspace navigation or visit `/admin/analytics`. Queries cover the whole instance, including unowned exports; ordinary users cannot access this page or its API.

This explorer counts accepted OTLP log records, not application stdout, metrics, traces, tokens or costs. Historical stdout is not imported. The independent analytics backend and the authenticated log receiver must both be configured before new client exports can appear. See [telemetry ingestion](../reference/telemetry-ingestion.md).

## Build a query

Choose the last hour, last 24 hours, last seven days, or a custom range. Presets end when **Run query** is pressed. Custom date fields use the explicit UTC offset, not the browser timezone. Both dates share that fixed offset; split queries when a daylight-saving transition requires different offsets. Results display UTC. Ranges include the start and exclude the end.

Select any combination of source, event name, severity, session ID and tool name. Selection order determines column order; use the earlier/later controls to reorder. Clear all dimensions for a single total. Optional minute, hour or day buckets split those counts over time.

Filters accept exact string values. Add each value before running; case and spaces are preserved. Multiple values within one dimension use OR, while separate dimensions use AND. Adding a blank input matches an explicitly empty string, not a missing attribute. Missing attributes can appear in grouped results but cannot currently be selected as filters.

Set the maximum result groups between 1 and 1,000. The limit includes time-bucket combinations. Exceeding it returns an error rather than a truncated result: narrow the range, add filters, remove grouping dimensions or raise the limit.

Queries run explicitly; there is no polling. Draft edits do not alter an in-progress request or the displayed successful result. Run again to apply them. Recoverable errors expose a retry action; lost administrator access clears protected results.

## Read results

The result header shows the executed range, filters, grouping and bucket settings. **Matching logs** sums the complete result; **Observed groups** counts distinct dimension combinations across buckets; **Result rows** includes their bucket combinations.

Only observed groups and buckets are shown; absent intervals are not filled with zeroes. A single ungrouped, unbucketed total can be zero. **Missing attribute** and **Empty string** are distinct values. These counts describe stored records, not deduplicated events: exporter retries can increase them.

An empty result can mean no clients have exported logs, ingestion is disabled, or the selected range and filters do not match. Analytics being available does not prove that clients are exporting. A disabled or failed analytics backend returns an error, never a fabricated zero.

## Development storage

Development Docker Compose enables analytics by default and stores `/app/data/analytics.sqlite3` on the existing named data volume. An explicit `UMBOD_TELEMETRY_ANALYTICS_ENABLED=false` still opts out. Application and Helm defaults remain disabled.

Compose forwards `UMBOD_OTLP_ENABLED`, `UMBOD_OTLP_BEARER_TOKEN` and `UMBOD_OTLP_MAX_REQUEST_BYTES` to the API. Ingestion stays disabled until explicitly enabled with a dedicated credential; analytics enablement does not silently permit unauthenticated exports. Configure clients for authenticated OTLP/HTTP JSON exports to `/v1/logs` on the API origin. Local Compose exposes this at `http://localhost:18010/v1/logs`, not the frontend port 3010.

Analytics has its own schema, connections and lifecycle, separate from the application database. The two files share the mounted volume, not a database runtime. Do not delete or replace the application database to reset analytics. Retention and deduplication are not implemented. Protect the volume and exported stdout according to the data collected; see [deployment configuration](../operations/configuration.md#analytics-backend).
