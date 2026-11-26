# Configuration

Use Helm values for deployment settings and Kubernetes Secrets for credentials. See the [generated Helm values reference](../reference/helm-values.md) for the full list of values, defaults, and allowed inputs.

## Profiles

| Helm value | Default | When to change it |
| --- | --- | --- |
| `config.profile` | `production` | Set to `local` for local evaluation. |
| `config.authentication.mode` | `auth0` | Set to `dev` for local evaluation; use OIDC on shared installations. |
| `config.logLevel` | `info` | Choose how much detail Umbod writes to its logs. |

For local evaluation, set both `config.profile=local` and `config.authentication.mode=dev`. Collect OpenTelemetry-compatible JSON logs from container standard output.

## Public origins

Use the addresses that browsers and agents actually reach, not internal Kubernetes Service addresses. Include `https://` (or `http://` for local testing), the hostname, and the port if needed. Leave off paths such as `/api` and `/mcp`.

| Helm value | Which address to use |
| --- | --- |
| `config.publicOrigins.site` | Where people open Umbod in a browser |
| `config.publicOrigins.api` | Where clients reach Umbod’s REST API |
| `config.publicOrigins.mcp` | Where agents connect to Umbod |

If redirects fail or the browser blocks API requests, check these addresses against your deployment. They also determine MCP URLs and OIDC metadata.

## Harness plugin installation

The **Getting started** page in Umbod offers plugins for Codex and Claude Code. On macOS and Linux (including WSL), the installer needs Bash, Python 3.8 or later, and curl. On Windows, it needs PowerShell 5.1 or later. Install Codex or Claude Code first. The plugin is installed for the current user only. The installer does not sign users in or check connected-app access. Use the supplied URL as-is; the inspect link opens the same configured script.

On custom ingress, allow unauthenticated GET/HEAD for `install.sh`, `install.ps1`, `package.zip`, `package.sha256`, `marketplace.txt`, and `endpoint.txt` under both `/api/install/v1/codex/` and `/api/install/v1/claude-code/`. Allow POST to `telemetry/redeem` under both paths without a browser session; it authenticates with a one-time bearer code. Forward `Authorization` without logging it. Keep `/api/me/telemetry/install-claims` and other protected routes behind normal authentication. Docker Compose supplies these routing rules.

If downloads fail, verify that the installing machine can reach `UMBOD_PUBLIC_API_ORIGIN` plus `/api/install/v1`, even if the browser fetched the script through a different `PUBLIC_API_BASE_URL` gateway. Scripts use `UMBOD_PUBLIC_MCP_ORIGIN` for the MCP URL and refuse mismatched package endpoints. Request headers and query parameters cannot override the configured URLs. Remote downloads and redemption require HTTPS; HTTP loopback is supported for development. Checksums detect corruption, not compromise of a server hosting both the package and checksum.

Telemetry is opt-in. The setup code is short-lived and single-use; the installer checks registration before redeeming it. In Codex, review the proposed changes and choose **Save Umbod telemetry as my Codex default** to replace user telemetry settings in `config.toml`, or finish without changing them. Neither choice starts Codex. Managed, project, environment-provided, or unverifiable settings are left untouched if a save would be unsafe. Claude Code writes logs-only settings to its protected user configuration; restart it after installation. Do not share or sync files containing tokens. To undo a Codex change, use the reported backup to restore telemetry settings without losing later edits, then revoke the token under **Settings → Access tokens**. Telemetry-only tokens expire after 30 days; run a fresh opt-in install to renew.

Review standalone Umbod MCP connections and conflicting marketplace registrations manually; installers do not replace them. Codex checks all configured local marketplaces, not the signed-in remote catalog, and verifies the selected marketplace after installation. An enabled plugin previously verified for the same Umbod instance can upgrade in place; if the upgrade fails, the installer keeps the old package and attempts to restore registration. Bash harness commands run noninteractively. If a step times out, check the last progress message and set `UMBOD_INSTALL_COMMAND_TIMEOUT` to an integer from 1 to 300 seconds if needed (default `45`). Downloads have a separate 120-second HTTP limit.

## Administrator MCP hosting

Keep `core.mcp.administrator.hosting=separate` (the default) to serve privileged tools on a private MCP listener with no public ingress. Its `core.mcp.administrator.port` defaults to `8013` and `core.mcp.administrator.baseUrl` to `http://localhost:8013`. Use `shared` only if you intend to host privileged tools on the public MCP endpoint. `config.features.mcp.administratorEnabled` must be enabled (the default) to make the tools available and start the separate listener. If the private listener is unreachable, check the feature flag and see [administrator MCP hosting](admin-mcp.md#hosting-and-deployment) for private access, port conflicts, environment defaults, and Compose shared-hosting opt-in.

## Persistence

SQLite is intended for development and evaluation. By default, persistence is off and data is lost when the core Pod is replaced. Set `persistence.enabled=true` to create a ReadWriteOnce PersistentVolumeClaim. Set `persistence.size`, `persistence.storageClass`, and `persistence.accessModes` to suit your storage, or set `persistence.existingClaim` to reuse a ReadWriteOnce claim.

Umbod does not migrate SQLite schemas or stored documents between incompatible versions. Back up any data you need and reset persistent storage before installing an incompatible version. Schedule `umbod cleanup` against the same persistent database before rollout. The servers do not automatically purge usage history or agent-behaviour data; see [scheduled cleanup](cleanup.md).

## Diagnostic reporting

Use **System settings → Agent diagnostics → Enable diagnostic reporting** and save the change to make the diagnostic tool, prompt, and playbooks available to eligible MCP clients. Turning it off blocks submissions without deleting saved instructions, patterns, or report history. A client that caches tools may still display the old tool until it refreshes, but Umbod rejects calls while reporting is off. Reporting requires an enabled playbook with at least one enabled pattern. Collection instructions guide the agent; they do not verify user consent.

New installations start with reporting off. Existing saved configurations are read as on if they had an enabled playbook, and off otherwise. Upgrade the API, MCP, and frontend together: older MCP workers do not honor the switch. Review it after upgrading if you relied on the former reporting mode.

Signed-in users can list their own diagnostic reports at `GET /api/me/agent-behaviour/reports` and retrieve a report by ID. If reports accepted by MCP are missing in REST, check that the issuer and subject match. With `UMBOD_AUTH=dev`, both services use the `sub` from `UMBOD_MCP_TEST_BEARER_TOKEN` (default subject `local-test-user`). If you customize the token, use the same token in both services and omit `iss` or set it to `urn:umbod:local`. `UMBOD_ADMIN_AUTHENTICATION_SIMULATED_USER_ID` is no longer used.

## Analytics backend

Enable analytics to store and query telemetry logs in the API. SQLite is the only supported backend.

| Helm value | Default | API environment variable |
| --- | --- | --- |
| `config.telemetryAnalytics.enabled` | `false` | `UMBOD_TELEMETRY_ANALYTICS_ENABLED` |
| `config.telemetryAnalytics.sqlitePath` | `/app/data/analytics.sqlite3` | `UMBOD_TELEMETRY_ANALYTICS_SQLITE_PATH` |

Use a canonical file path under the mounted data directory, not an in-memory database, the application database, its sidecar files, or aliases to them. `core.api.env` overrides take precedence but must keep the files separate. Both database files use the same volume, not separate claims. Enable `persistence.enabled` to retain analytics across core Pod replacements.

Enabling analytics does not start the log receiver. If logs are missing, check [collector setup for your chart version](telemetry-ingestion.md#helm-collector-deployment) and verify that clients can reach it. Keep the ingestion token in a Kubernetes Secret, not in chart values.

## Advertised telemetry endpoint

Set `telemetry.publicBaseUrl` (`UMBOD_OTLP_PUBLIC_BASE_URL`, blank by default) to tell clients where to send logs. Compose defaults to `http://localhost:14318`. Use the externally reachable base URL, including any proxy prefix, but omit `/v1/logs`; Umbod appends it. Only absolute HTTPS URLs and HTTP loopback URLs (`localhost`, IPv4 loopback, or `::1`) are accepted. Do not include credentials, a query, a fragment, whitespace, control characters, or an invalid host or port. Trailing slashes are removed.

Setting this URL does not enable the receiver or open ingress. Check **Public collector base URL** in configuration inspection or call `GET /api/me/telemetry/setup` as an authenticated user eligible to own personal access tokens. It returns `status: available` and `logs_endpoint` when enabled and configured, or `status: unavailable` with `reason: disabled` if the receiver is off, otherwise `reason: not_configured` if the URL is blank. Responses are not cached. `available` does not test reachability; check the URL and ingress from the client network. Umbod does not guess a URL from other settings or request headers. Existing receivers can still run with a blank public URL. See [telemetry setup discovery](telemetry-ingestion.md#authenticated-setup-discovery).

## Filesystem runtime

File content can live on local disk or S3. The application database still stores file names, ownership, and access grants. Keep the database and matching content storage together to preserve access to files.

### File size limits

| Environment variable | Helm value | Default | Controls |
| --- | --- | --- | --- |
| `UMBOD_FILESYSTEM_UPLOAD_MAX_BYTES` | `config.filesystem.uploadMaxBytes` | `10485760` bytes (10 MiB) | File uploads, independently of MCP connector file-input limits |
| `UMBOD_FILESYSTEM_PREVIEW_MAX_BYTES` | `config.filesystem.previewMaxBytes` | `1048576` bytes (1 MiB) | Raw bytes for browser previews and complete MCP resource reads, not full REST downloads |

Use positive integers. The preview environment variable and both Helm values have a maximum of `9007199254740991`. Helm applies the limits to API and MCP and sends the preview limit to the frontend. Do not override them in `core.api.env` or `core.mcp.env`; the chart rejects it. Replace the retired `config.filesystemPreviewMaxBytes` key with `config.filesystem.previewMaxBytes`. Restart affected services and reload the browser; check the frontend preview limit at `/app-config.json`.

If a large upload fails despite the API limit, check every gateway on the upload path. The frontend nginx proxy limits the entire request body to 12 MiB; direct API ingress does not pass through that proxy. The upload limit is not a storage quota.

### MCP file deletion approval

`UMBOD_REQUIRE_MCP_FILE_DELETION_APPROVAL` defaults to unset. Set it to `true` or `false` to provide a deployment default for the administrator filesystem settings. Restart the services after changing the environment value; it is read at startup. An administrator override takes precedence. Resetting the override restores the deployment default, or the built-in `true` if the variable is unset.

This policy applies only to new direct `filesystem_delete_file` MCP calls. It does not affect browser deletion or pending MCP approvals. If MCP cannot read the stored policy, it still requires approval.

### Content storage

| Environment variable | Default | When to set it |
| --- | --- | --- |
| `UMBOD_FILESYSTEM_CONTENT_BACKEND` | `local` | Set to `s3` to store content in a bucket. |
| `UMBOD_FILESYSTEM_CONTENT_DIRECTORY` | `filesystem-content` under `UMBOD_DATA_DIR` (default `.data`) | Set a nonblank local directory to override it. S3 ignores it during normal operation but can use it as the migration source. |
| `UMBOD_FILESYSTEM_S3_BUCKET` | empty | Required for S3. Use a pre-existing general-purpose bucket. |
| `UMBOD_FILESYSTEM_S3_REGION` | `us-east-1` | Set the signing region. |
| `UMBOD_FILESYSTEM_S3_ENDPOINT_URL` | empty | Leave empty for AWS endpoint resolution, or set a credential-free HTTP(S) endpoint for an S3-compatible service. |
| `UMBOD_FILESYSTEM_S3_PREFIX` | empty | Use a relative prefix with no leading or trailing slash and no empty, `.` or `..` segments. |
| `UMBOD_FILESYSTEM_S3_ADDRESSING_STYLE` | `auto` | Choose `auto`, `virtual`, or `path`. Compatible services may require `path`. |

For local storage, relative paths stay relative and `~` expands to the home directory. Workers sharing one application database must share the same content directory. For S3, use identical bucket, region, endpoint, prefix, and addressing style in API and MCP. Use HTTPS outside trusted local test networks. Nondefault S3 settings cannot be used with the local backend.

In Helm, set storage variables in both `core.api.env` and `core.mcp.env`; there are no dedicated values. Provide credentials through `existingSecret` or workload identity. Umbod uses the AWS SDK credential chain, including environment credentials and profiles. Compose forwards storage settings and AWS access-key, secret-key, and session-token variables to both services. Provision the bucket and encryption policy separately. Grant `s3:GetObject`, `s3:PutObject`, and `s3:AbortMultipartUpload` on the selected object prefix, plus any required KMS permissions. Bucket creation and listing permissions are not needed.

To switch from local storage to S3, stop API and MCP, run the [offline migration](s3-file-storage.md#migrate-existing-local-content), then configure both services for S3 and restart them. For other backend, bucket, or prefix changes, plan a migration that preserves the content keys recorded in the database. There is no automatic migration or fallback. See [S3 file-content storage](s3-file-storage.md) for setup and permissions.

If an uploaded file is missing, check that the upload session completed: storing the file does not make it visible in Umbod. Zero-byte uploads are allowed; duplicate names are rejected rather than overwritten. The creator owns the file, which inherits applicable recursive grants, not folder-only grants. Failed publication can leave unreferenced content; Umbod does not automatically remove it. Configure S3 bucket lifecycle rules to abort abandoned multipart uploads.

On versions that support direct S3 transfers, clients upload to storage and receive short-lived download URLs after Umbod checks access. Do not forward Umbod credentials to storage or log signed URLs. See [S3 file storage](s3-file-storage.md) for release availability, [direct uploads](s3-file-storage.md#direct-upload-sessions), and [direct downloads](s3-file-storage.md#direct-downloads).

## Authentication and secrets

Use OIDC for shared installations. Configure the provider under `config.authentication.oidc.domain`, `config.authentication.oidc.clientId`, `config.authentication.oidc.audience`, and `config.authentication.oidc.requiredScopes`. Configure access under `config.authorization.adminGroup`, `config.authorization.adminMembershipClaim`, and `config.authorization.mcpPermissionClaim`.

Create a Kubernetes Secret containing `UMBOD_ROOT_SECRET` and `UMBOD_OIDC_CLIENT_SECRET`, then set `existingSecret` to its name. Do not put secret values in a Helm values file.

!!! warning
    `UMBOD_ROOT_SECRET` is the source of all derived backend security secrets. Rotating it invalidates derived credentials.

### Server startup requirement

Set a nonblank `UMBOD_ROOT_SECRET` in the environment or `.env` even for `local`/`dev`. Umbod does not generate it. API and MCP must use the same value and keep it stable across restarts. If either service refuses to start, check for a missing, empty, or whitespace-only value. `umbod api serve` and `umbod mcp serve` check before binding HTTP ports, including in reload mode. This cannot prevent sockets managed outside Umbod from binding. Default Compose rejects missing or empty values before starting services; Umbod rejects whitespace-only values at startup.

`umbod config show` and `umbod config validate` can inspect or validate a local configuration without a secret. That does not mean the servers can start. Production validation remains strict.

## Personal connections identity policy

Personal connections let users authorize a published connector against their own downstream account. See [Shared and Personal connectors](../using-umbod/connectors.md) for publishing, sign-in, and tool discovery.

| Environment variable | Default | When to set it |
| --- | --- | --- |
| `UMBOD_PERSONAL_CONNECTIONS_ENABLED` | `auto` | Set to `false` to disable personal registration, or `true` to require it and fail validation if prerequisites are missing. |
| `UMBOD_PERSONAL_CONNECTIONS_IDENTITY_NAMESPACE` | empty | Set a stable namespace for the identity authority. Use the same value in REST and MCP. |
| `UMBOD_PERSONAL_CONNECTIONS_OAUTH_ENABLED` | `auto` | Set to `false` to disable downstream authorization, or `true` to require it and fail validation if prerequisites are missing. |

Both switches accept `auto`, `true`, or `false`. Automatic registration needs a namespace. Only `local`/`dev` automatic selection with an exactly empty namespace uses `test:umbod-local`; explicit `true` requires a supplied namespace. Production and real providers have no fallback. Development semantic JWT verification or simulation requires a `test:` namespace with a nonblank suffix and does not provide real-account sign-in. Production rejects development verification and simulation. An invalid namespace or unsafe authentication fails validation. Compose forwards the modes, namespace, and optional SQLite path to API and MCP.

Registration requires REST and MCP authentication. Production needs real REST JWT verification, `UMBOD_OIDC_ISSUER_URL`, `UMBOD_OIDC_AUDIENCE`, a configured or derived `UMBOD_ADMIN_JWKS_URL`, MCP OIDC, and Google, Auth0, or Entra. An Auth0 domain can supply the issuer. Present issuers must match the configured upstream issuer exactly; only Google upstream tokeninfo claims can omit `iss`. Google and Auth0 require a verified nonblank `sub`. Entra uses the configured tenant and verified `oid`, requires a matching `tid` and delegated `scp`, and does not use `sub` for ownership. Machine-only identities are not supported.

Choose a distinct namespace per identity authority and keep it across restarts and upgrades. Changing it changes who owns saved connections. Do not derive it from request issuer, email, client ID, or the outer MCP proxy URL. Do not enable personal writes while older workers still run.

If registration is available but downstream authorization is not, check that all API workers share the same persistent, non-memory SQLite database, SQLite-compatible locking, and the same nonblank `UMBOD_ROOT_SECRET`. Separate Pod-local databases are unsupported. In `auto`, missing storage or encryption disables authorization without disabling registration. Registration set to `false` also disables automatic authorization; explicitly enabling authorization while registration is off is invalid. Configuration inspection shows the resulting on/off values.

For downstream OAuth setup:

- Use a provider with protected-resource and issuer metadata and S256 PKCE. Set requested scopes and choose public dynamic registration or a preconfigured public or confidential client pinned to its issuer. For a confidential client, choose Basic or POST explicitly; there is no registration or authentication fallback. Granted scopes cannot exceed requested scopes.
- Expose `/api/oauth/downstream-mcp/callback` and `/api/oauth/downstream-mcp/callback/issuer/<digest>` under `UMBOD_PUBLIC_API_ORIGIN` without gateway authentication. The callback base comes from this setting, not forwarded headers. The generic route requires a matching issuer parameter. For providers without issuer-bearing callbacks, Umbod uses the issuer-specific route, where `<digest>` is the lowercase SHA-256 hex digest of the exact discovered issuer. That route can omit the issuer parameter only when it matches the saved issuer binding. Register the exact selected URI with preconfigured clients. Use HTTPS in production; trusted local/dev simulation can use validated HTTP loopback.
- Redact callback queries, secret-bearing administrator request bodies, and `Authorization` headers in ingress, proxies, tracing, and error reporting. Application redaction cannot protect earlier logs.
- If users still cannot run tools, check administrator publication and connector-level group grants, then user enablement, downstream sign-in, and private tool discovery. Umbod attempts initial private tool discovery after sign-in; users can retry or refresh tools. Personal connector grants cover all tools the downstream user can discover, including newly discovered tools; per-tool administrator approval or activation is not required. Automatic feature availability does not connect accounts or grant consent.

## Optional user-profile enrichment

Keep `access_claims` unless your gateway can supply a separate ID token for Umbod to verify and use for display fields. These environment settings have no dedicated Helm values.

| Environment variable | Default | Purpose |
| --- | --- | --- |
| `UMBOD_USER_PROFILE_MODE` | `access_claims` | Select `access_claims` or `id_token`. |
| `UMBOD_USER_PROFILE_JWT_HEADER` | `X-Auth-Request-ID-Token` | Dedicated raw ID-token header; never use Authorization or the configured access header. |
| `UMBOD_USER_PROFILE_NAME_CLAIM` | `name` | Display-name claim key |
| `UMBOD_USER_PROFILE_EMAIL_CLAIM` | `email` | Email claim key |
| `UMBOD_USER_PROFILE_PICTURE_CLAIM` | `picture` | Picture claim key |

Claim mappings use literal keys, including namespaced keys, not dot paths. Blank mappings and invalid or conflicting header names prevent startup. `id_token` requires real production JWT authentication, an OIDC issuer, admin JWKS URL, and OIDC client ID. It is incompatible with development verification, simulation, and disabled authentication.

Gateways must overwrite client-supplied credential headers and keep profile tokens out of browser responses. Compose sends ID tokens separately, leaves Authorization and the access header for access tokens, and defaults to `access_claims` so development authentication still works. The dedicated ID-token header does not fall back to Authorization.

If `/api/me/profile` shows access-token fields instead of ID-token fields, check the header and token. The ID token must use RS256, include `iss`, `aud`, `exp`, and `sub`, and use the client ID as audience, not the API audience. Its issuer and subject must match the verified access token. `azp` is required for multiple audiences and, whenever present, must match the client ID. Missing or rejected ID tokens fall back to verified access claims. Rejection logs show only a category, not the token; authentication debug logs report only credential presence.

The response is not cacheable. The access subject always determines `user.id`. `capabilities.administration` reflects the administrator policy and verified access claims, or unrestricted administration if administrator authentication is explicitly disabled. Unauthenticated requests get 401; a missing or rejected profile token does not cause a 401 by itself or grant access. A valid ID token with missing fields yields `unknown` for name and null for email or picture, without mixing sources or calling UserInfo. Use `/api/me/profile`, not the retired `/api/admin/users` route.

## Images

Set `core.image` and `frontend.image` to the images shipped with the chart release. Do not use floating tags.

## Connector plugins

Set `plugins.image` to the plugin-bundle image and `plugins.availableConnectorIds` to the connector IDs you want to allow. See [Connector plugins](../plugins/index.md) for the lifecycle and security model.

## Source of truth

The published chart and [generated Helm values reference](../reference/helm-values.md) define the supported Helm settings.
