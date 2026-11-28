---
description: Day-two tasks for a self-hosted Umbod, such as scheduled cleanup, backup, upgrades, administrator MCP, ports, and limits.
---

# Operate

Day-two tasks for a self-hosted installation. Commands assume the `umbod` namespace and release name from [Install for a team](install.md).

## Schedule cleanup

Umbod does not delete expired data on its own. Run `umbod cleanup` every hour against the live database:

```bash
kubectl -n umbod exec deploy/umbod-core -c api -- umbod cleanup
```

Run it from your scheduler of choice. Do not let runs overlap, and alert when a run fails or is missed.

| Job | Deletes |
| --- | --- |
| Usage retention | Usage events older than `UMBOD_PERSONAL_USAGE_RETENTION_DAYS` (default 90) |
| Diagnostics retention | Diagnostic reports after 30 days and their receipts after 60 days |

Cleanup does not remove telemetry logs, file contents, or incomplete S3 uploads.

**Check:** the command exits with status `0`. A nonzero status means at least one job failed. Run it again: repeating cleanup is safe.

Each job has 5 seconds by default. Raise `UMBOD_CLEANUP_JOB_TIMEOUT_SECONDS` (up to 3600) if jobs time out.

## Back up and upgrade

Umbod keeps its state in two places. Back them up together, because one is useless without the other:

| State | Where |
| --- | --- |
| Application database (names, permissions, connector settings) | The persistent volume, mounted at `/app/data` |
| File contents | The same volume, or your [S3 bucket](s3.md) |

To upgrade:

1. Back up the database and the file contents.
2. Rerun the `helm upgrade --install` command from [Install](install.md#4-install) with the new `--version`. Keep the same secret and values file.
3. Rerun the [checks](install.md#5-check).

Umbod does not migrate the database between incompatible versions. Rehearse an upgrade on a copy first.

### Upgrading from 0.0.1-beta.9

- **Administrator MCP:** it moved to a [private listener](#administrator-mcp). The tools are now `admin_discover`, `admin_inspect`, and `admin_apply`.
- **Files over MCP:** read file contents with `resources/read`, not `filesystem_read_file`. New folder shares are recursive unless you pass `recursive: false`.
- **Telemetry:** remove any public `/v1/*` route and point exporters at the [private collector](telemetry.md).
- **Files outside a namespace** are no longer visible. Their contents are not deleted. Export them before you upgrade.

## Map provider values to Umbod groups

Create and manage Umbod groups in **Administration → Groups**. A Group ID is an Umbod identifier and cannot be changed after creation.

OAuth sign-ins get ordinary group permissions only from saved mappings. After deploying without mappings, sign in as an administrator and open **System settings → Group mappings**. For each group whose access should be restored, enter the provider claim value, select the corresponding Umbod group, and save. A value identical to a Group ID still needs a mapping. Existing groups and their permissions do not need to be recreated.

Umbod uses the configured OAuth issuer and `UMBOD_MCP_PERMISSION_CLAIM` for all mappings. Review saved mappings before changing either setting. Administrator membership is configured separately and does not depend on mappings. The Google MCP adapter does not currently expose the upstream issuer, so ordinary group mappings do not apply to those sign-ins.

Saved changes take effect on subsequent REST and MCP requests without a restart. Removing all mappings revokes ordinary OAuth group access. The API and MCP workers must share the same application database, as they do in the standard Helm and Compose installations. Separate in-memory stores do not share saved mappings.

## Administrator MCP

Administrators can manage Umbod from an agent through three tools: `admin_discover`, `admin_inspect`, and `admin_apply`. They are served on a separate, private listener.

1. Forward the listener:

    ```bash
    kubectl -n umbod port-forward service/umbod-mcp-administrator 8013:8013
    ```

2. Add `http://localhost:8013/mcp` to your agent and sign in as an administrator.

**Check:** the agent lists `admin_discover`.

| To | Set |
| --- | --- |
| Turn the tools off | `config.features.mcp.administratorEnabled=false` |
| Serve them on the public MCP endpoint | `core.mcp.administrator.hosting=shared` |
| Use another port or origin | `core.mcp.administrator.port` and `.baseUrl`, and register `<baseUrl>/auth/callback` with your OIDC provider |

Never add a public ingress for the private listener.

## Services and ports

| Service | Port | Exposure |
| --- | ---: | --- |
| Workspace (`umbod-frontend`) | `3000` | Public at `/` |
| REST API (`umbod-api`) | `8000` | Public at `/api`. Keep the prefix |
| MCP (`umbod-mcp`) | `8011` | Public at `/mcp` |
| Administrator MCP (`umbod-mcp-administrator`) | `8013` | Private |
| Telemetry collector | `4318` | Private, off by default |
| Metrics | `8001`, `8012` | Private |

API and MCP run in one Pod and share one data volume. The workspace runs separately.

## Limits

| Limit | Default | Change with |
| --- | --- | --- |
| File upload size | 10 MiB | `config.filesystem.uploadMaxBytes`. Raise your gateway's body limit too |
| File preview and MCP read size | 1 MiB | `config.filesystem.previewMaxBytes` |
| Approval before an agent deletes a file | On | `UMBOD_REQUIRE_MCP_FILE_DELETION_APPROVAL` |

## Personal connectors

[Personal connectors](../use/connectors.md#add-an-mcp-server) need a stable identity namespace. Set `UMBOD_PERSONAL_CONNECTIONS_IDENTITY_NAMESPACE` to the same value in `core.api.env` and `core.mcp.env`, and never change it: it decides who owns saved connections.
