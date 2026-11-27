---
type: Feature Specification
title: Personal activity read API
description: One owner-scoped API for harness activity and Umbod MCP usage without combining the underlying counts.
---

# Personal activity read API

## Overview

- `GET /api/me/activity` accepts `days=7` or `days=30` and defaults to seven days. Both sources use the same half-open UTC calendar window, including today and ending at the next midnight. `as_of` anchors the window, not a database snapshot or an event cutoff.
- Given a signed-in user, return separate `harness` and `mcp` sections. MCP retains the existing usage summary, including tool, resource, and prompt counts, daily totals, and ranked tools. Harness counts observed tool and file-tool outcomes and skill activations. Both sources rank tools before returning the top five.
- Given one source unavailable at request time, return HTTP 200 with its section marked `unavailable`, not zero. Available sources may legitimately have zero counts. Given both sources are unavailable, return HTTP 503 with both statuses. Existing startup readiness requirements are unchanged.

## Harness sessions

- `GET /api/me/activity/sessions` accepts the same `days`, optional literal search `q`, optional `cursor`, and `limit` from 1 to 100 (default 20). Only owner-attributed Claude Code and Codex sessions with nonblank session IDs are eligible. Session IDs are limited to 1,024 characters and must be usable in the detail URL; NUL and the standalone dot segments `.` and `..` are excluded. A session key contains its source and session ID.
- Given a selected window, group all eligible logs by session, not just tool events. Return first and last observed event times within the window and counts of successful, failed, and unknown tool outcomes. These times are not a claim about when the process started or ended.
- Given a search term, trim surrounding whitespace before matching it case-insensitively as a literal substring of a session ID, source, client label, or first observed UTC date. Search before pagination. Order by most recent observed activity descending, then source and session ID ascending. The cursor binds the account, range, search, and last sort key. A malformed or mismatched cursor returns HTTP 422; later pages reuse the original date window but read live data.
- `GET /api/me/activity/sessions/{source}/{session_id}` returns the selected session across all retained observations. Include the outcome counts, top five named tools, up to 100 named failure groups with counts and a truncation flag, and the skill activation count. A foreign and a nonexistent session have the same HTTP 404 response. A harness outage returns HTTP 503 for both session routes.

## Boundaries

- Derive ownership using the existing authenticated identity and each store's own key. Never accept a caller-supplied owner or include unowned exports. Personal reads are not cacheable.
- All three successful Activity responses and the typed overview HTTP 503 include a top-level opaque `identity_key` from the verified caller. It matches `GET /api/me/profile` for the same account; it is not a storage owner ID.
- A harness tool outcome without an explicit result counts as unknown, not cancelled. Unnamed tool events contribute to outcome totals but not named rankings. Skill names are not collected by this feature.
- The facade composes the current usage rollups and normalized telemetry. It does not change ingestion, count the sources together, or match executions to harness sessions.

## Dashboard and navigation

- `/dashboard` is the single destination for standard personal activity, using the [Activity overview and session routes](../api/src/umbod/rest/activity/README.md). The two sources share a 7/30-day selector but never share a total.
- Select MCP Activity by default. Keep the selected source when the user changes the period or refreshes.
- In Harness activity, show a collapsible **Search session** picker above the charts. Selecting a session replaces the overview with that session’s retained activity and hides the period selector. Returning to the overview restores the prior period and picker results.
- Keep reads scoped to the verified account, discarding stale data and requests on account changes. `/insights/activity` redirects to `/dashboard`; Agent behaviour and advanced Log analytics remain under Insights.

## Endpoint migration and cleanup
- `GET /api/me/usage` is retired: it returns HTTP 404 to signed-in users and is absent from the personal OpenAPI document. Use the Activity overview's `mcp.summary` for the MCP summary at seven or thirty days. MCP usage ingestion, persistence, configuration, and retention are unchanged.
- Keep `POST /api/me/telemetry/log-counts` for custom personal log queries. Use the Dashboard for the standard 7/30-day summaries. Keep the Log analytics presets for custom time ranges, grouped results, and distinctions the facade does not expose, such as read versus edit. Do not retire the count endpoint unless those capabilities are replaced or explicitly dropped. The instance-wide administrator endpoint is out of scope.
