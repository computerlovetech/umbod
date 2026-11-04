# S3 file-content storage

Use S3 to store the bytes of [Umbod files](../using-umbod/files.md) separately from the application database. Names, folders, upload sessions, owners, and grants remain in the database. S3 does not replace SQLite or make the current single-replica chart a production database architecture.

!!! warning "Implementation and release availability"
    S3 support is being implemented. This guide describes the current source configuration, not a guarantee that the published image contains it. Select an immutable core image containing the S3 driver before enabling this backend; do not assume the chart's default image supports it.

## Prepare storage

1. Provision a general-purpose S3 bucket and choose a region and optional object prefix. Umbod does not create buckets.
2. Allow both API and MCP containers to reach the storage endpoint. Use HTTPS outside trusted local test networks.
3. Provision credentials with `s3:GetObject`, `s3:PutObject`, and `s3:AbortMultipartUpload` permissions on the selected object prefix. Bucket creation and listing are not required. Add the permissions required by your encryption policy, including KMS access where applicable.
4. For S3-compatible services, confirm support for the driver's object and multipart operations, including conditional publication with `If-None-Match: *`.
5. Configure lifecycle cleanup for incomplete multipart uploads. Completed but unreferenced objects require a separate retention/cleanup plan.

## Configure Helm values

The chart has **no dedicated `filesystem` or `s3` values block**. Pass non-secret application settings through **both** `core.api.env` and `core.mcp.env`. Each environment variable below is a key in each map, with its configured value as a scalar string.

| Environment key in both maps | Required setting or default |
| --- | --- |
| `UMBOD_FILESYSTEM_CONTENT_BACKEND` | Set to `s3`; the application default is `local` |
| `UMBOD_FILESYSTEM_S3_BUCKET` | Set to the pre-existing bucket name |
| `UMBOD_FILESYSTEM_S3_REGION` | Set to the bucket's signing region; default `us-east-1` |
| `UMBOD_FILESYSTEM_S3_PREFIX` | Optional object prefix; default empty |
| `UMBOD_FILESYSTEM_S3_ENDPOINT_URL` | Leave empty for AWS endpoint resolution, or set the S3-compatible service's endpoint |
| `UMBOD_FILESYSTEM_S3_ADDRESSING_STYLE` | `auto` by default; `virtual` or `path` also supported |
| `UMBOD_FILESYSTEM_UPLOAD_MAX_BYTES` | Optional positive upload limit; default `10485760` bytes |

A prefix must be relative, with no leading/trailing slash, empty path segments, or dot segments. Endpoints must not contain credentials, query strings, or fragments. S3-compatible services may require `path` addressing.

Keep `UMBOD_FILESYSTEM_CONTENT_DIRECTORY` if already configured: S3 ignores it during normal operation, and the migration CLI can use it to locate the old local content. Nondefault S3 settings with the local backend still fail configuration validation.

Set these chart values alongside the two environment maps:

| Helm value | Configuration |
| --- | --- |
| `core.image.repository` | Repository containing the S3-capable Umbod core image |
| `core.image.tag` | Immutable tag for that image, used by both API and MCP |
| `existingSecret` | Name of a separately provisioned Kubernetes Secret in the release namespace |
| `persistence.enabled` | `true` to retain the application database across Pod replacement |
| `persistence.size`, `persistence.storageClass` | Size and storage class suitable for the database; no longer the capacity for S3 file bytes |
| `persistence.existingClaim` | Optional existing ReadWriteOnce claim instead of creating one |

Keep backend, bucket, region, endpoint, prefix, addressing style, and upload-limit settings identical in API and MCP. The Helm schema accepts the environment maps but does not validate S3 semantics or equality between containers; application validation happens at startup.

Apply your values file using the [Helm installation workflow](../getting-started/kubernetes-installation.md#configure-a-shared-installation). Consult the [Helm values reference](../reference/helm-values.md) for chart constraints. The chart runs API and MCP together in one fixed, single-replica core Pod.

## Supply credentials securely

The S3 driver uses the AWS SDK credential-provider chain. Umbod does not copy AWS credentials into its application configuration.

For environment-based credentials, provision the Secret named by `existingSecret` with:

| Secret key | Purpose |
| --- | --- |
| `UMBOD_ROOT_SECRET` | Required nonblank application security root; stable across restarts and shared by API and MCP |
| `UMBOD_OIDC_CLIENT_SECRET` | OIDC client secret when required by the deployment's authentication setup |
| `AWS_ACCESS_KEY_ID` | Storage access key |
| `AWS_SECRET_ACCESS_KEY` | Storage secret key |
| `AWS_SESSION_TOKEN` | Required when using temporary session credentials |

The chart imports this Secret into both backend containers, not the frontend. Do not put credentials in `core.api.env`, `core.mcp.env`, endpoint URLs, or committed values files. Explicit container environment entries override imported Secret values, so remove stale credential overrides. Temporary environment credentials need external renewal and container replacement; Umbod is not their issuer or rotation service.

### Workload identity

An externally managed service account can be selected with `serviceAccount.create=false` and `serviceAccount.name` set to that account. This selection alone does not configure AWS identity.

The chart-created account has no annotation wiring, and the core Pod explicitly disables automatic service-account-token mounting. Changing `serviceAccount.automountServiceAccountToken` alone does not override that Pod setting. Workload identity therefore requires provider-specific provisioning and credential/token injection. Verify that **both containers** receive the SDK's required identity environment and token access before relying on it.

## Verify the deployment

After upgrading, check that both backend containers start successfully without configuration or credential errors. Then use an authorized user to:

1. Upload a small file and complete publication.
2. List the new node and read its bytes through an authenticated REST client or supported MCP read tool.
3. Confirm that a user without a matching grant cannot read it.
4. Restart the core Pod and confirm the same file is still listed and readable.

Storage authentication can be lazy: healthy startup alone does not prove bucket access. A successful round trip exercises database publication and content storage together. Avoid logging credentials, authorization headers, or file content while diagnosing failures.

## Migrate existing local content

Use `umbod migrate files-to-s3` from an image containing the migration command. This is an offline, non-destructive content copy, not a database migration or an automatic configuration cutover.

1. Record the current local content directory. Its default is `filesystem-content` beneath `UMBOD_DATA_DIR`; preserve any existing directory override.
2. Stop **all** API/MCP services and other file writers. Keep them stopped through inventory, copying, verification, and cutover. The command cannot enforce this externally; `--offline` acknowledges that responsibility.
3. Back up the application database and local content together. Run a temporary migration container using an image containing the CLI, the same original storage volume, and the deployment's required configuration/secrets. Set `UMBOD_FILESYSTEM_CONTENT_BACKEND=s3` and the destination S3 settings **for this container only**. Do not start API/MCP services yet. The existing `UMBOD_FILESYSTEM_CONTENT_DIRECTORY` can remain configured.
4. Optionally run `umbod migrate files-to-s3 --offline --dry-run` to inspect the inventory without writing S3 objects. The source defaults to `UMBOD_FILESYSTEM_CONTENT_DIRECTORY`, or `filesystem-content` beneath `UMBOD_DATA_DIR` if unset. Use `--source` to override it. Confirm that the resolved source is the complete original directory and that the destination bucket/prefix are correct.
5. Run `umbod migrate files-to-s3 --offline` and require exit status zero. Keep any `--source` override identical to the dry run. Each new object is read back and verified by size and SHA-256; existing objects are skipped only when identical. Conflicting content fails without overwriting. Failed or interrupted runs can be rerun with the same source and destination; completed objects are verified again.
6. Configure **both** API and MCP to use that exact S3 destination, restart them, and verify existing files and a new upload using the deployment checks above. Retain the source and backups until your retention policy permits separate cleanup.

### Coolify operating order

1. Prepare the migration-capable image, bucket and credentials before the outage.
2. Stop both API and MCP in Coolify and prevent automatic restarts/deployments. Back up their persistent data.
3. From the server terminal, run the temporary migration container described above with the **existing Coolify volume** and S3 configuration. Do not create a new Compose project/empty volume. No shell inside the application image is required; invoke the `umbod` executable directly.
4. After migration succeeds, set the same S3 backend, bucket, region, endpoint, prefix, addressing style and credentials for **both** services in Coolify. Keep the local directory setting if present. The migration command copies content; it does not update Coolify settings or switch running services.
5. Redeploy/start both services. Read an existing file, upload and read a new one, and confirm ownership/sharing before reopening access.

Retain the database volume: S3 replaces file contents, not the database. Retain the old local files and backups until separate cleanup is approved.

The inventory includes every canonical immutable object in the local directory, including unreferenced objects and staged upload content. It ignores `.content-` temporary files, rejects invalid entries and symlinks, and does not infer completeness from database references. Check that the mounted source is the correct, complete deployment directory. Logical content keys, database records, ownership and grants remain unchanged. The command neither deletes local content nor changes deployment configuration. Dry runs still require S3 read access and stopped writers. No bucket listing or object deletion permissions are needed; S3 HEAD checks use the object read permission. AWS may return 403 rather than 404 for absent keys without `s3:ListBucket`; if that occurs, grant appropriately scoped listing permission for migration preflight. Permission errors are never treated as missing content.

Do not resume writes against local storage after cutover and expect S3 to stay synchronized. Rolling back after new S3-only uploads requires a separately planned reverse migration; this command only copies local content to S3.

## Operational boundaries

- **Transfers pass through Umbod.** S3 is a backend driver; there are no direct browser-to-S3 uploads, presigned URLs, or client-managed multipart/resumable transfers.
- **Back up metadata and content together.** Without persistence, replacing the core Pod loses namespace and permission records even if the bucket survives.
- **No automatic migration or fallback.** Use the offline migration procedure above for local-to-S3 cutover. Other backend, bucket or prefix changes require a separate migration. Merely changing values makes existing content unavailable.
- **No automatic physical cleanup.** Publication happens after content storage; failures can leave unreferenced immutable objects. File deletion removes namespace/policy records, not the stored object. Multipart abort is best effort, so process termination can leave incomplete parts. Lifecycle cleanup of multipart uploads does not reclaim completed orphan objects.
- **Limits remain separate.** The default filesystem limit is 10 MiB. MCP upload and read tools have their own limits. The frontend nginx proxy caps request bodies at 12 MiB; raising the application limit also requires corresponding proxy/gateway changes. Direct API ingress bypasses that frontend proxy but may impose its own limits.

The backend change does not change file ownership, sharing, or publication rules. New files remain private, parent grants do not inherit, and uploads are invisible until explicit completion. See [Files](../using-umbod/files.md) for user and administrator behavior.
