# Downstream MCP REST

This module owns downstream MCP REST delivery. Administrator routes, authenticated personal-user routes and the public state-bound callback remain independently mounted with their existing URLs and authentication policies. Folder ownership does not merge access boundaries.

`personal_connections/` owns personal catalogue, enablement, disconnect and durable OAuth routes. Its [index](personal_connections/README.md) describes request-scoped composition and callback protections. `rest/main.py` mounts these separately from administration; they are not included in the administrator router exported by this package.

## Administration

`routes.py` exposes connector creation, projections, publication, deletion and capability administration under `/api/admin/connectors/mcp`. `schemas.py` defines strict request and response contracts; `dependencies.py` creates request-scoped application services.

`POST /personal-oauth` accepts the existing `metadata` object and a `configuration` object containing `endpoint_url` and optional `oauth_configuration`. Endpoint-only requests preserve empty-scope dynamic public registration. OAuth settings contain administrator-approved `requested_scopes` and an explicit `client` variant: `dynamic_public`, `preconfigured_public` or `preconfigured_confidential`. Static clients require exact `issuer_url` and `client_id`; confidential clients additionally require a nonblank `client_secret` and explicit Basic/POST token authentication. Downstream user credentials, owner identifiers and ownership overrides are rejected. Creation requires `personal_connections.enabled`; disabled deployments return 404 with `personal_connections_unavailable` before writes. It returns 201 with personal ownership, unpublished status, unknown health and no shared credentials, without probing the endpoint.

Detail, summary and configuration responses include `authorization_mode` (`shared` or `personal`). Personal definitions always report `credential_configured=false`. Generic metadata/configuration edits and ownership conversion remain unsupported; publication and deletion remain available. Publication does not discover capabilities or enable execution.

`GET` and `PUT /{connector_id}/personal-oauth` read and replace the separate OAuth configuration. GET exposes a revision, requested scopes and nonsecret client fields; confidential responses expose only `client_secret_configured`. PUT requires `expected_revision` and complete `settings`, including a fresh secret for confidential configurations. Effective changes or explicit confidential rotation atomically erase personal authorizations and attempts while preserving user enablement, publication and grants. Stale writes return 409. Confidential writes require a configured encryption secret. `personal_validation.py` sanitizes validation errors on personal administrator writes without altering shared-route errors; no submitted secret or Pydantic input document is reflected.

Group permission composition in `rest/mcp_permissions/dependencies.py` decorates the downstream permission catalogue with published personal connector targets, without adding capability targets.
