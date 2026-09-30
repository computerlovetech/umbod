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

## Admin MCP tools for connector configuration

Administrators can configure **existing native, OpenAPI, and downstream MCP connectors** through the same remote MCP endpoint used by agents (see [Endpoints and ports](../reference/endpoints-and-ports.md)). These tools require an access token whose `config.authorization.adminMembershipClaim` includes `config.authorization.adminGroup`. Both tools accept `connector_kind` values `native`, `openapi`, and `downstream_mcp`. They do not create connectors or change publication, credentials, or discovery.

| Tool | Inputs | Result |
| --- | --- | --- |
| `read_connector_configuration` | `connector_kind`, `connector_id` | Current capability activation and invocation policies, description state, and group permissions. |
| `upsert_connector_configuration` | `connector_kind`, `connector_id`, `desired_state` | Applies the requested changes and returns the resulting configuration. |

Read the state first to obtain capability keys and current revisions. For upsert, supply `desired_state` as an object with an `operations` array. Each operation has an `operation` discriminator:

- `set_capability_activation`: select `capability_kind` and `capability_key`, then set `activation_status` to `enabled` or `disabled`.
- `set_capability_invocation_policy`: select a tool and set `mode` to `direct` or `ask`, with its `expected_revision`.
- `set_capability_description` / `use_system_capability_description`: override the connector's capability description or restore the system description, with its `expected_revision`.
- `update_group_permissions`: set a group's `connector_status` and/or individual capability permissions (`enabled` or `disabled`).

Upserts are partial: omitted settings remain unchanged, and an empty `operations` array reads the current state without changing it. Revision-guarded updates require the revision returned by the latest read; rejected changes surface as MCP tool errors. Activating a capability does not by itself grant an agent access: the connector and capability also need the appropriate group permissions.

Reads include known capabilities even when disabled. Activation and grants also support prompts, resources, and resource templates where the connector catalog supplies them; invocation policies apply only to tools. Mixed-operation writes are transactional: invalid targets and stale revisions leave all requested settings unchanged. Reapplying an unchanged description or policy does not advance its revision.

MCP configuration writes append REST-equivalent activation, invocation-policy, description-override, and permission change events in the same transaction as the settings. Unchanged targets emit no events; rejected or rolled-back writes leave neither settings nor events committed. Running processes consume these durable events through the existing synchronization workers. Native administration includes registered connectors even when unavailable for runtime use.

## Source of truth

The published chart values and the [generated Helm values reference](../reference/helm-values.md) are the source of truth for supported operator configuration.
