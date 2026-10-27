# Group permission administration

Authenticated administration routes under `/api/admin/mcp-permissions`.

- `routes.py`: assignable-target queries, group reads and aggregate permission mutations.
- `dependencies.py`: request-scoped store, reader and permission-catalogue composition.
- `schemas.py`: HTTP request and response models.
- `mappers.py`: HTTP/domain translation and mutation error mapping.

## Assignable-target reads

Only GET `/assignable-targets` uses `get_assignable_permission_catalog`. It creates fresh cache instances through the public infrastructure factory. FastAPI shares `get_assignable_publication_reader` within that request, so all connector kinds and personal connector listing reuse publication checks. OpenAPI and downstream capability catalogues are wrapped once, and both enumeration and readiness resolve through their captured complete-identity indexes.

Native catalogues retain their existing in-memory indexes. Configuration readiness remains unchanged. Activation checks remain fresh per capability and are not memoized or batched in this iteration. Personal definitions still use their existing separate listing.

The response is a read-only projection, not authorization authority or an atomic database snapshot. Cache instances are discarded with the request, and subsequent requests observe committed publication, activation and catalogue changes. No credentials or group grants are cached by these wrappers.

## Mutations and other reads

`get_admin_group_permission_management` continues to consume the uncached `get_connector_permission_catalog`. Registration, deletion, permission updates, group detail and legacy group-list routes do not use the cached GET dependency. Existing target validation, persisted permission behavior, events and invocation checks are unchanged.

The cached and uncached dependency paths share composition helpers but explicitly select different reader wrappers. No request-method inspection, application-state cache, implicit database interception or cross-request reuse is involved.

## Verification

`tests/umbod/rest/mcp_permissions/test_assignable_permission_request_cache.py` checks response contents, per-request query budgets and freshness on both persistence backends. For its single shared downstream connector with N enabled tools, reads and sessions fall from 4N+4 to N+5: one publication read, two definition reads, one catalogue read, one empty OpenAPI inventory read and N distinct activation reads. This is a bounded fixture result, not a universal endpoint budget.

Core wrapper tests verify lookup identity, missing/conflicting results, failed-load retry, cached false publication values, schema-copy isolation and namespace separation.
