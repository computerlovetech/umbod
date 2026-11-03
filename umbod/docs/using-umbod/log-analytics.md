---
type: User Guide
title: Log analytics
description: Count ingested telemetry logs with administrator-owned filters, grouping and UTC time buckets.
---

# Log analytics

Administrators can open **Log analytics** in workspace navigation or visit `/admin/analytics`. Queries cover the whole instance, including unowned exports; ordinary users cannot access this page or its API.

This explorer counts accepted OTLP log records, not application stdout, metrics, traces, tokens or costs. Historical stdout is not imported. The analytics backend and authenticated private collector must both be enabled before new client exports can appear. The API host shares one analytics runtime between collector writes and administrator queries; an external `umbod telemetry serve` deployment owns separate storage whose history is not automatically visible here. See [telemetry ingestion](../reference/telemetry-ingestion.md).

## Build a query

Choose the last hour, last 24 hours, last seven days, or a custom range. Presets end when **Run query** is pressed. Custom date fields use the explicit UTC offset, not the browser timezone. Both dates share that fixed offset; split queries when a daylight-saving transition requires different offsets. Results display UTC. Ranges include the start and exclude the end.

Select any combination of source, event name, severity, session ID and tool name. Selection order determines column order; open **Advanced** to reorder multiple groups. Clear all dimensions for a single total. Optional minute, hour or day buckets split those counts over time.

Select **+ Add filter**, choose a field, then search and select values observed in the selected time range. Counts beside values cover that range without other filters applied. Selected values appear as removable chips; case and spaces are preserved. Multiple values within one field match any of those values; different fields apply together. **Empty value** matches an explicitly empty string, not a missing attribute. Missing attributes can appear in grouped results but cannot be selected as filters.

If the time range changes, select **Refresh values** before choosing more filters. Value discovery supports up to 1,000 groups; if there are too many, narrow the time range. Searching filters the loaded choices, not the full log history.

Under **Advanced**, set the maximum result groups between 1 and 1,000. The limit includes time-bucket combinations. Exceeding it returns an error rather than a truncated result: narrow the range, add filters, remove grouping dimensions or raise the limit.

Queries run explicitly; there is no polling. Draft edits do not alter an in-progress request or the displayed successful result. Run again to apply them. Recoverable errors expose a retry action; lost administrator access clears protected results.

## Read results

Results show the executed range and filters, with grouping and interval settings beneath the table. **Matching logs** sums the complete result; **Groups** counts distinct dimension combinations across buckets.

Only observed groups and buckets are shown; absent intervals are not filled with zeroes. A single ungrouped, unbucketed total can be zero. **Missing attribute** and **Empty string** are distinct values. These counts describe stored records, not deduplicated events: exporter retries can increase them.

An empty result can mean no clients have exported logs, ingestion is disabled, or the selected range and filters do not match. Analytics being available does not prove that clients are exporting. A disabled or failed analytics backend returns an error, never a fabricated zero.

## Development storage

Development Docker Compose enables analytics by default and stores `/app/data/analytics.sqlite3` on the existing named data volume. An explicit `UMBOD_TELEMETRY_ANALYTICS_ENABLED=false` still opts out. Application and Helm defaults remain disabled.

Compose forwards `UMBOD_OTLP_ENABLED`, `UMBOD_OTLP_BEARER_TOKEN` and `UMBOD_OTLP_MAX_REQUEST_BYTES` to the API. Ingestion stays disabled until explicitly enabled with a dedicated credential; analytics enablement does not silently permit unauthenticated exports. Configure clients for authenticated OTLP/HTTP JSON or protobuf exports to `/v1/logs` on the private collector origin. Local Compose forwards this only at `http://127.0.0.1:14318/v1/logs`, not public REST port 18010 or frontend port 3010.

Analytics has its own schema, connections and lifecycle, separate from the application database. The two files share the mounted volume, not a database runtime. Do not delete or replace the application database to reset analytics. Retention and deduplication are not implemented. Protect the volume and exported stdout according to the data collected; see [deployment configuration](../operations/configuration.md#analytics-backend).
