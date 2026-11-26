# Store files in S3

Use S3 to store file bytes in a bucket instead of on local disk. Keep the application database persistent: it still holds files’ names, ownership, and access rules. Use an Umbod image that includes the S3 driver.

## Set up a bucket

1. Create a general-purpose bucket. Grant the runtime identity `s3:GetObject`, `s3:PutObject`, and `s3:AbortMultipartUpload` for the selected prefix, plus any permissions required by your encryption policy.
2. Use the same settings in API and MCP. With Helm, set the variables below in both `core.api.env` and `core.mcp.env`.
3. Supply credentials through the AWS SDK credential chain, such as `existingSecret` or externally configured workload identity. Do not put credentials in chart values. Confirm that both containers receive them.
4. Enable persistence, then verify that an authorized user can upload and read a file, an unauthorized user cannot read it, and the file survives a core Pod restart.

| Setting | Value |
| --- | --- |
| `UMBOD_FILESYSTEM_CONTENT_BACKEND` | `s3` |
| `UMBOD_FILESYSTEM_S3_BUCKET` | Existing bucket name |
| `UMBOD_FILESYSTEM_S3_REGION` | Signing region; default `us-east-1` |
| `UMBOD_FILESYSTEM_S3_PREFIX` | Optional relative object prefix without leading or trailing slashes or dot segments |
| `UMBOD_FILESYSTEM_S3_ENDPOINT_URL` | Optional credential-free endpoint for S3-compatible storage |
| `UMBOD_FILESYSTEM_S3_ADDRESSING_STYLE` | `auto` by default; some compatible services need `path` |

Use HTTPS outside trusted local environments. For compatible storage, verify object and multipart operations. Configure lifecycle cleanup for incomplete multipart uploads. Umbod does not automatically reclaim unreferenced completed objects.

## Migrate existing local content

The `umbod migrate files-to-s3` command is not included in Umbod `0.0.1-beta.9`. Do not switch an existing local deployment to S3 until you have an image with the migration command.

1. Stop all file writers, including API and MCP. Back up the application database and file contents together. Keep writers stopped through verification and cutover.
2. In a temporary container with the original volume, use an image that includes `umbod migrate files-to-s3`. Give that container the destination S3 settings and credentials. Keep the existing content directory setting, or pass `--source` if needed.
3. Run `umbod migrate files-to-s3 --offline --dry-run` to inspect the inventory, then `umbod migrate files-to-s3 --offline` with the same source and destination. The copy verifies content and does not overwrite conflicts. A failed or interrupted copy can be rerun with the same settings.
4. After a successful copy, configure both API and MCP for the same S3 destination, restart them, and verify an existing file and a new upload. Keep the old local content and backups. The command does not delete, switch, or synchronize storage; rolling back after new S3 uploads requires a separate migration.

## Direct upload sessions

Direct S3 uploads are not included in Umbod `0.0.1-beta.9`; these steps require a newer image that supports signed transfers.

With S3, upload sessions normally return a short-lived presigned PUT. Clients send the original bytes with the returned headers and exact declared length, without forwarding Umbod credentials or following redirects. For S3-compatible storage, verify that signed PUTs enforce conditional creation (`If-None-Match: *`). Browser uploads need bucket CORS for the frontend origin, PUT, and the required headers. The client must be able to reach the storage endpoint; do not rewrite signed URLs.

The uploader must complete the session with Umbod after PUT. Umbod verifies the stored bytes and current permissions before publishing. If PUT has an uncertain outcome, attempt authenticated completion instead of blindly replaying it. See [upload transfers](../using-umbod/files.md#uploading-from-an-agent) for the shared retry rules.

## Direct downloads

Direct S3 downloads are not included in Umbod `0.0.1-beta.9`.

Verify that S3-compatible storage supports presigned GET with response-header overrides. On a supported image, an authorized REST download can redirect to a presigned S3 GET valid for at most five minutes. Keep the bucket private and treat the URL like a credential: it can remain usable until expiry even if Umbod access is revoked. Do not log signed URLs or forward Umbod credentials to S3. Use `?delivery=stream` on the content endpoint when bytes must pass through Umbod. MCP resource reads are unchanged.
