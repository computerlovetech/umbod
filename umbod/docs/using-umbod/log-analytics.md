---
type: User Guide
title: Log analytics
description: Review reported tool calls, file-tool calls and skill activations by session, or build a custom log query.
---

# Log analytics

Administrators can open **Log analytics** in workspace navigation or visit `/admin/analytics`. Queries cover the whole instance, including unowned exports; ordinary users cannot access this page or its API.

This explorer counts accepted OTLP log records, not application stdout, metrics, traces, tokens or costs. Historical stdout is not imported. The analytics backend and authenticated private collector must both be enabled before new client exports can appear. The API host shares one analytics runtime between collector writes and administrator queries; an external `umbod telemetry serve` deployment owns separate storage whose history is not automatically visible here. See [telemetry ingestion](../reference/telemetry-ingestion.md).

## Session activity reports

Choose **Tool calls**, **File activity** or **Skill activity** and a time range, then run the report. Standard reports start with **All sessions**; no session ID is needed. Reports group by source and session together so identical session IDs from different sources do not merge.

Select a session in the results to focus the report on that exact session ID. Select **All sessions** to clear the selection. Both actions keep the executed report and absolute time range, even if draft settings have changed, and return to the first page. Session filtering applies across sources; rows remain separated by source. Running a report again applies the current settings across all sessions.

- **Tool calls** counts recognized completed-tool events, including file-tool calls, grouped by source, session and outcome. Successful, failed and unknown outcomes are separate rows; permission decisions are not completed calls. Outcomes come from explicit result attributes, never log severity.
- **File activity** counts recognized read-tool and edit-tool calls, grouped by source and session. These are calls, not distinct files or necessarily successful operations. Repeated calls count again, and one edit may affect multiple files. Shell commands, implicit reads and unrecognized tools are not classified as file activity.
- **Skill activity** counts dedicated skill activation or invocation events by source and session. It does not count distinct skills, skill installations, reads of skill files, or the Skill tool as a substitute for activation events.

Missing source or session attributes are shown as **Not reported**. Missing or empty session IDs cannot be selected for drill-down. An empty report means no matching activity was reported; it does not establish that the agent performed none. Client versions and exporter settings determine which events are available. See [supported telemetry mappings](../reference/telemetry-ingestion.md#normalized-activity-fields).

## Time range and pagination

Choose the last hour, last 24 hours, last seven days, or a custom range. Time-range presets end when the report or custom query is run. Custom date fields use the explicit UTC offset, not the browser timezone. Both dates share that fixed offset; split queries when a daylight-saving transition requires different offsets. Results display UTC. Ranges include the start and exclude the end.

Results show up to 100 aggregate rows per page. Use **Previous** and **Next** below the results to navigate; running a report or custom query starts again at the first page. A session can have several rows or span pages. Each row is a complete count for its grouping; report totals describe only the current page.

The analytics API accepts page sizes from 1 to 1,000 completed aggregate rows, including time-bucket combinations. Each response includes `has_more`, not query-wide totals. Keep the executed time range and other query settings fixed while paging. Reads are live rather than a snapshot: late ingestion can change counts and ordering, so successive pages may repeat or skip rows.

Queries run explicitly; there is no polling. Draft edits do not alter an in-progress request or the displayed successful result. Run again to apply them. Recoverable errors expose a retry action; lost administrator access clears protected results.

## Custom log query

Choose **Custom log query** to explore raw logs or fields not covered by a report. Select any combination of source, event name, severity, session ID, tool name, activity kind and outcome. Selection order determines column order. Clear all dimensions for a single total. Optional minute, hour or day buckets split those counts over time. Switching reports does not overwrite custom query settings.

Select **+ Add filter**, choose a field, then search and select values observed in the selected time range. Counts beside values cover that range without other filters applied. Selected values appear as removable chips; case and spaces are preserved. Multiple values within one field match any of those values; different fields apply together. **Empty value** matches an explicitly empty string, not a missing attribute. Missing attributes can appear in grouped results but cannot be selected as filters.

For manual session filtering, choose **Session ID** in the filter picker, enter an exact ID and select **Add session filter**. This adds a removable filter without requiring the ID to appear in discovered values.

If the time range changes, select **Refresh values** before choosing more filters. Value discovery reads pages of observed groups. Searching filters the loaded choices, not the full log history. Unrecognized events remain available here without inferred activity or outcome.

## Read results

Results show the executed range and filters, with grouping and interval settings beneath the table. Counts and group summaries describe loaded rows, not query-wide totals.

Only observed groups and buckets are shown; absent intervals are not filled with zeroes. A single ungrouped, unbucketed total can be zero. **Missing attribute** and **Empty string** are distinct values. These counts describe stored records, not deduplicated events: exporter retries can increase them.

An empty result can mean no clients have exported logs, ingestion is disabled, or the selected range and filters do not match. Analytics being available does not prove that clients are exporting. A disabled or failed analytics backend returns an error, never a fabricated zero.

## Development storage

Development Docker Compose enables analytics by default and stores `/app/data/analytics.sqlite3` on the existing named data volume. An explicit `UMBOD_TELEMETRY_ANALYTICS_ENABLED=false` still opts out. Application and Helm defaults remain disabled.

Compose forwards `UMBOD_OTLP_ENABLED`, `UMBOD_OTLP_BEARER_TOKEN` and `UMBOD_OTLP_MAX_REQUEST_BYTES` to the API. Ingestion stays disabled until explicitly enabled with a dedicated credential; analytics enablement does not silently permit unauthenticated exports. Configure clients for authenticated OTLP/HTTP JSON or protobuf exports to `/v1/logs` on the private collector origin. Local Compose forwards this only at `http://127.0.0.1:14318/v1/logs`, not public REST port 18010 or frontend port 3010.

Analytics has its own schema, connections and lifecycle, separate from the application database. The two files share the mounted volume, not a database runtime. Do not delete or replace the application database to reset analytics. Retention and deduplication are not implemented. Protect the volume and exported stdout according to the data collected; see [deployment configuration](../operations/configuration.md#analytics-backend).
