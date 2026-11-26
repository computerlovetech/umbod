# Configuration

Use Helm values for deployment settings and Kubernetes Secrets for credentials. See the [Helm values reference](../reference/helm-values.md) for defaults and allowed inputs, and the [installation guide](../getting-started/kubernetes-installation.md) for deployment steps.

## Public origins

Use `config.profile=local` and `config.authentication.mode=dev` only for local evaluation. Shared installations should use production configuration and OIDC.

Set `config.publicOrigins.site`, `.api`, and `.mcp` to the addresses browsers and agents can reach. Include the scheme and any nondefault port, but omit paths such as `/api` and `/mcp`. Check these origins when redirects or browser requests fail.

## Authentication and secrets

Configure the OIDC provider under `config.authentication.oidc` and configure administrator membership and MCP access under `config.authorization`. Put `UMBOD_ROOT_SECRET` and the production OIDC client secret (`UMBOD_OIDC_CLIENT_SECRET`) in the Secret selected by `existingSecret`, not in chart values.

API and MCP need the same nonblank `UMBOD_ROOT_SECRET` at startup, including in local development. Keep it stable across restarts; rotation invalidates derived credentials. A successful local `umbod config validate` does not prove both servers can start.

## Administrator MCP hosting

The Helm steps below require a chart that lists `core.mcp.administrator` in `helm show values`; chart `0.0.1-beta.9` does not include the separate administrator Service.

Keep the default `core.mcp.administrator.hosting=separate` for privileged tools on a private listener. Sign in with the configured administrator membership; network access alone is not enough. For the default Helm release, run `kubectl port-forward service/umbod-mcp-administrator 8013:8013` and connect to `http://localhost:8013/mcp`. Do not add public ingress. For a different port or client origin, set `core.mcp.administrator.port` and `.baseUrl`; register the separate origin’s `/auth/callback` with your OIDC provider. Use HTTPS outside loopback.

Set hosting to `shared` only to expose these tools on ordinary MCP. To disable the tools and the private listener, set `config.features.mcp.administratorEnabled=false`. Source deployments select hosting with `UMBOD_MCP_ADMINISTRATOR_HOSTING`; the listener belongs to `umbod mcp serve`. Compose publishes the separate listener only on loopback; use `docker-compose.mcp-shared.yml` with the base Compose file to opt into shared hosting (Compose 2.24.4 or newer).

**Check:** Sign in as an administrator and confirm `tools/list` includes `admin_discover` on the configured endpoint. In separate mode, also check that ordinary MCP does not list it.

## Persistence

Enable `persistence.enabled=true` or the core Pod loses its SQLite data when replaced. Set the storage size and class, or use `persistence.existingClaim` for an existing ReadWriteOnce claim. Keep the application database even when files use S3.

Back up data before upgrades. Umbod does not migrate SQLite schemas or stored documents between incompatible versions. Configure [scheduled cleanup](cleanup.md) separately.

## Harness plugin installation

Use the [Codex plugin guide](../using-umbod/codex-plugin.md) for installation and opt-in telemetry. Installer downloads and the advertised MCP URL come from the configured public API and MCP origins; verify reachability from the installing machine.

On custom gateways, allow unauthenticated GET/HEAD for `install.sh`, `install.ps1`, `package.zip`, `package.sha256`, `marketplace.txt`, and `endpoint.txt` under `/api/install/v1/codex/` and `/api/install/v1/claude-code/`. Allow POST to `telemetry/redeem` under those paths without a browser session; forward its one-time bearer code without logging it. Keep `/api/me/telemetry/install-claims` and other protected routes authenticated. Docker Compose already configures these exceptions.

## Diagnostic reporting

Agent diagnostics are not included in Umbod `0.0.1-beta.9`. Use a deployment with the **Agent diagnostics** settings and the `report_diagnostic` MCP tool.

New installations start with reporting off. In **System settings → Agent diagnostics**, enable reporting and configure an enabled playbook with at least one enabled pattern. Turning reporting off blocks submissions without deleting instructions or reports. See the [agent diagnostics MCP reference](../reference/built-in-tools.md#agent-diagnostics) for the tool and receipt contract.

Upgrade API, MCP, and frontend together; older MCP workers do not honor this switch. Existing saved configurations default to on if they had an enabled playbook. Users can read their own reports at `/api/me/agent-behaviour/reports`; if a report is missing, check that the API and MCP identities have the same issuer and subject. In dev mode, use the same `UMBOD_MCP_TEST_BEARER_TOKEN` in both services.

**Check:** Sign in to ordinary MCP, read a live playbook, and explicitly ask the agent to submit a test report using only authorized, non-sensitive context. A successful submission returns a `report_id` receipt. Finding the playbook alone does not confirm reporting works.

## Analytics backend

[Set up the private collector and analytics](telemetry-ingestion.md) separately. Enable `config.telemetryAnalytics.enabled` to query stored logs, and use a separate SQLite file on the persistent data mount.

### Advertised telemetry endpoint

`telemetry.publicBaseUrl` advertises the collector to eligible signed-in users; it does not enable ingestion or expose a route.

## Filesystem runtime

`config.filesystem.uploadMaxBytes` defaults to 10 MiB; `config.filesystem.previewMaxBytes` defaults to 1 MiB and also limits MCP resource reads. Set the Helm values rather than overriding each service’s environment. Check gateway body limits before increasing the upload limit.

MCP file deletion requires approval by default. An administrator can override the policy, or set the deployment default using `UMBOD_REQUIRE_MCP_FILE_DELETION_APPROVAL`. Changes only affect new direct MCP calls, not pending approvals or browser deletion.

With local storage, API and MCP must share the same content directory (`filesystem-content` under `UMBOD_DATA_DIR` by default). To use a bucket, follow the [S3 setup and offline migration guide](s3-file-storage.md). Do not change storage backends or prefixes without copying the existing content.

For API-based upload transfers, exempt only `PUT /api/filesystem/uploads/{upload_id}/transfer` from browser login at the gateway. Umbod still validates the transfer capability. Keep session creation, inspection, and completion behind normal authentication.

## Personal connections identity policy

Use the same stable `UMBOD_PERSONAL_CONNECTIONS_IDENTITY_NAMESPACE` in API and MCP. Changing it changes who owns saved connections. `UMBOD_PERSONAL_CONNECTIONS_ENABLED` and `UMBOD_PERSONAL_CONNECTIONS_OAUTH_ENABLED` accept `auto`, `true`, or `false`; `true` fails validation when prerequisites are missing. Production requires verified REST and MCP authentication. Downstream authorization also requires shared persistent SQLite and the same root secret across API workers.

Use a provider with issuer and protected-resource discovery and S256 PKCE. Allow callbacks at `/api/oauth/downstream-mcp/callback` and its `/issuer/<digest>` variant without gateway authentication, using the configured public API origin. Register the exact callback URI for preconfigured clients. Do not log callback queries or credentials. See [connector setup and access](../using-umbod/connectors.md) for the publishing and user sign-in flow.

## Optional user-profile enrichment

Keep `UMBOD_USER_PROFILE_MODE=access_claims` unless the gateway supplies a separate, verifiable ID token. In `id_token` mode the default header is `X-Auth-Request-ID-Token`. Keep it separate from Authorization, overwrite caller-supplied credential headers at the gateway, and do not return either token to the browser.

An accepted ID token only supplies display fields. Its issuer and subject must match the access token, and its audience must be the OIDC client ID. If it is missing or rejected, `/api/me/profile` falls back to verified access claims; authorization is unchanged.
