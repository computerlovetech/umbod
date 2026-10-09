# Configuration

Configure Umbod through Helm values and Kubernetes Secrets. Review the [generated Helm values reference](../reference/helm-values.md) for every supported value, default, and schema constraint.

## Profiles

| Helm value | Default | Purpose |
| --- | --- | --- |
| `config.profile` | `production` | Selects local or production behavior |
| `config.authentication.mode` | `auth0` | Selects development authentication or an OIDC provider |
| `config.logLevel` | `info` | Sets application logging verbosity |

For local evaluation, set `config.profile=local` and `config.authentication.mode=dev`. Application services emit OpenTelemetry-compatible JSON logs to standard output for collection by the Kubernetes container runtime.

## Public origins

Set origins without a trailing path:

| Helm value | Purpose |
| --- | --- |
| `config.publicOrigins.site` | Browser-facing Umbod origin |
| `config.publicOrigins.api` | Browser-facing REST API origin |
| `config.publicOrigins.mcp` | Agent-facing MCP origin |

These values drive API and MCP URLs, allowed browser origins, OIDC metadata, and authentication redirects. They must match the URLs visible to users and MCP clients.

## Persistence

Umbod uses SQLite for development and evaluation. Persistence is disabled by default, so data is lost when the core Pod is replaced.

Set `persistence.enabled=true` to create a ReadWriteOnce PersistentVolumeClaim. Configure `persistence.size`, `persistence.storageClass`, and `persistence.accessModes` as required, or set `persistence.existingClaim` to use an existing ReadWriteOnce claim.

Umbod does not migrate SQLite schemas or persisted documents between incompatible versions. Reset persistent storage before installing an incompatible Umbod version.

## Authentication and secrets

Shared installations require an OIDC provider and stable secrets. Configure non-secret authentication settings with the typed `config` Helm values, including:

- `config.authentication.oidc.domain`
- `config.authentication.oidc.clientId`
- `config.authentication.oidc.audience`
- `config.authentication.oidc.requiredScopes`
- `config.authorization.adminGroup`
- `config.authorization.adminMembershipClaim`
- `config.authorization.mcpPermissionClaim`

Create a Kubernetes Secret containing `UMBOD_ROOT_SECRET` and `UMBOD_OIDC_CLIENT_SECRET`, then set `existingSecret` to its name. Do not place secret values directly in a Helm values file.

!!! warning
    `UMBOD_ROOT_SECRET` is the sole derivation root for backend security secrets. Rotating it invalidates derived credentials.

## Optional user-profile enrichment

The application environment contract supports optional enrichment of `/api/admin/users`; the Helm chart has no dedicated profile values. Access tokens remain the sole authentication and membership authority. The response keeps `id`, `email`, `name`, and `picture`; `id` always comes from the verified access subject.

| Environment variable | Default | Contract |
| --- | --- | --- |
| `UMBOD_USER_PROFILE_MODE` | `access_claims` | `access_claims` or `id_token` |
| `UMBOD_USER_PROFILE_JWT_HEADER` | `X-Auth-Request-ID-Token` | Dedicated ID-token header, never Authorization or the configured access header |
| `UMBOD_USER_PROFILE_NAME_CLAIM` | `name` | Exact literal display-name claim key |
| `UMBOD_USER_PROFILE_EMAIL_CLAIM` | `email` | Exact literal email claim key |
| `UMBOD_USER_PROFILE_PICTURE_CLAIM` | `picture` | Exact literal picture claim key |

Mappings apply to the selected profile source and support namespaced keys without dot traversal. Blank mappings and invalid or conflicting header names fail startup. ID-token mode requires real production JWT authentication, a configured OIDC issuer, admin JWKS URL, and OIDC client ID. It is rejected with development semantic verification, simulation, or disabled authentication.

ID tokens require RS256, exact issuer, client-ID audience (not the API audience), and `iss`, `aud`, `exp`, and `sub`. Multiple audiences require `azp` matching the client ID; any present `azp` must match. Verified ID issuer and subject must match verified access issuer and subject. The dedicated header has no Authorization fallback and expects the raw ID token.

Missing profile headers preserve access-only clients. Present invalid, expired, incorrectly addressed, or identity-mismatched profile tokens are ignored in full; a structured warning records only a rejection category, and verified access claims provide the fallback. Profile failures never cause their own 401 or grant permissions. Valid ID tokens with unavailable fields return `unknown` name and nullable email/picture rather than mixing sources. No UserInfo network lookup is performed. Profile verification shares a root-lifespan JWKS cache through Starlette's yielded lifespan state mapping and request-state dependencies, with single-flight locking, a five-minute TTL, five-second unknown-key/failure refresh cooldown, and a three-second fetch timeout. A new key ID can trigger an early refresh; concurrent requests reuse its result. `/users` executes synchronous profile lookups in FastAPI's threadpool so key-fetch delays do not block unrelated event-loop requests. Authentication debug mode logs only credential-presence booleans, including configured access/profile headers, not tokens, header values, identity fields, or decoded JWT contents.

Gateways must overwrite client-supplied credential headers and prevent profile token exposure in browser responses. Compose exports ID tokens separately while keeping Authorization and the access header bound to access tokens; its default mode stays `access_claims` so development authentication continues to work.

## Images

The chart selects the released core and frontend images through `core.image` and `frontend.image`. Use the image tags shipped with the chart release. Do not use floating tags.

## Connector plugins

Configure a plugin-bundle image with `plugins.image` and allow its connector IDs with `plugins.availableConnectorIds`. See [Connector plugins](../plugins/index.md) for the lifecycle and security model.

## Source of truth

The published chart values and the [generated Helm values reference](../reference/helm-values.md) are the source of truth for supported operator configuration.
