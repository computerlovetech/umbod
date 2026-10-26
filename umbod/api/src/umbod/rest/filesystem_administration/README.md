# Filesystem root access administration

- `routes.py` mounts GET/PUT `/api/admin/filesystem/root-access` through the existing authenticated admin application. Its route boundary sanitizes validation, stale/conflict and unknown failures, including dependency construction and response serialization.
- `deps.py` prepares the shared runtime database and creates a management service per request through the public infrastructure factory.
- `models.py` adds `suggested_issuer` and MCP `group_claim` hints to the core view. Routes suggest `urn:umbod:local` only under the shared configured local/dev simulation policy; otherwise they preserve the exact configured OIDC issuer, empty when unconfigured.
- `__init__.py` exposes the admin router.

GET is strictly read-only and returns constant root UUID, explicit uninitialized/ready/conflict status, opaque revision, editable direct groups and read-only recursive groups. PUT requires expected_revision and a complete explicit group list. Models reject extra fields, blank keys, duplicate keys and empty permission sets; an empty group list is valid.

The admin panel can initialize and repeatedly edit access without CLI use. Existing admin membership and cookie CSRF safeguards apply, including development admin simulation. No additional upstream-verification requirement applies to configuration. Exact submitted issuers are configuration, not token identity; hints never fall back to administrator claims. Ordinary filesystem routes require upstream-verified users or the explicitly configured local-development identity resolver, and receive no administrator bypass. Local Test User access requires an explicit GROUP grant under issuer `urn:umbod:local`; simulation itself creates no root owner or grants.

Policy responses, including authentication and CSRF failures, are no-store. Errors use filesystem_policy_stale (409), filesystem_policy_conflict (409), filesystem_policy_invalid (422), or filesystem_policy_storage_failure (500) without reflecting submitted data or storage exceptions. Management is not exposed under user or MCP routes.
