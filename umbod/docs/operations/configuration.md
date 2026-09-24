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

## Images

The chart selects the released core and frontend images through `core.image` and `frontend.image`. Use the image tags shipped with the chart release. Do not use floating tags.

## Connector plugins

Configure a plugin-bundle image with `plugins.image` and allow its connector IDs with `plugins.availableConnectorIds`. See [Connector plugins](../plugins/index.md) for the lifecycle and security model.

## Source of truth

The published chart values and the [generated Helm values reference](../reference/helm-values.md) are the source of truth for supported operator configuration.
