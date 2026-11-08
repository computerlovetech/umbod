---
type: Reference
title: Filesystem upload transfers
description: Byte-preserving uploads coordinated by MCP and transferred over HTTP.
---

# Filesystem upload transfers

## Scope

`filesystem_begin_upload` and `filesystem_complete_upload` coordinate the existing filesystem upload lifecycle. Existing filesystem tools, including the inline `filesystem_upload`, remain available. These tools do not accept local paths or read the agent's machine.

## Coordination and transfer

When the user has not chosen a destination, resolve their personal home through the `home` operation of `filesystem_browse` and use its returned node UUID. Inspect caller permissions and distinguish direct policy visibility from manageable sharing. The [homes and permissions reference](filesystem-homes-and-permissions.md) describes safe agent destination selection.

The client computes the local file's exact byte size and, preferably, its SHA-256 programmatically. Begin accepts the existing parent UUID, filename, metadata, declared size, and an optional lowercase hexadecimal `expected_sha256`. It returns an upload identifier, transfer deadline, and raw HTTP PUT instructions. With S3 storage, begin defaults to a presigned storage URL. With local storage, it returns the API capability endpoint. Clients follow the returned URL and headers rather than assuming a particular destination. The selected transfer endpoint must be reachable by the client.

The client streams the original file with the returned headers, without redirect following, cookies, or MCP bearer credentials. Direct S3 PUTs require the exact declared content length; browser clients derive it from the original `File`, while other clients must send a known-length body. File bytes do not belong in either MCP tool call. Session uploads use the configured filesystem upload limit and the selected transfer service's limits; the existing inline tool retains its separate 10 MiB ceiling.

Complete requires the authenticated caller that owns the session. Publication remains private and atomic. The result includes node metadata, the verified byte count, SHA-256, and an MCP resource link. The receipt describes the bytes published by that upload. Resource reads resolve current authorized content and retain their separate 1 MiB limit; larger files require HTTP download.

## Transfer authority

For API transfers, the `X-Umbod-Upload-Token` header is a secret capability for PUT to one upload's exact transfer endpoint. Only its digest is retained. Its lifetime is at most 15 minutes and never exceeds the upload session deadline. It cannot authorize completion, session inspection, downloads, or other filesystem operations.

For S3 transfers, the presigned URL is the secret capability. Its signature binds a server-selected object key, exact content length, content type and `If-None-Match: *`. It grants no Umbod session or publication authority. Transfer instructions expire within 15 minutes and are not renewed by session inspection. Umbod persists the transfer identity and deadline, not the signed URL. Do not remove signed headers or rewrite the destination URL.

API transfer admission checks the stored user identity, including issuer, and the group membership delegated at initiation. Current filesystem grants are checked before and after API byte transfer. Upstream group-membership changes are not refreshed during this bounded delegation. Direct S3 URLs cannot recheck Umbod authorization during PUT: already issued URLs may store bytes until they expire even after permission revocation. Completion checks a fresh authenticated caller and current authorization before any file is published.

API transfer endpoint responses and responses bearing transfer instructions use `Cache-Control: no-store`. Treat the whole presigned URL and returned headers as secrets and do not cache them or include them in logs, diagnostics or unrelated HTTP requests. Unlike API capability tokens, S3 signatures necessarily appear in the returned URL's query string; never copy that URL into ordinary navigation or observability metadata.

## Retries and verification

Begin is not idempotent. A lost begin response does not justify blindly creating another session.

For API transfers, only one transfer can claim a session at a time. Failed or interrupted transfers release their matching claim for retry. A successful transfer consumes its capability and cannot be replaced by replaying PUT. A worker crash after a durable claim can leave the upload conflicting; restart recovery of abandoned claims is not provided. Start a new session when that outcome is established rather than claiming the original upload succeeded.

For S3 transfers, conditional creation prevents replacement after the first successful PUT, even before publication. A lost PUT response does not justify replaying the upload or beginning another session: attempt authenticated completion to verify the existing object. Session inspection can still report pending until that verification succeeds. A failed verification publishes nothing. If immutable stored content is incorrect, inspect the error and start a new session rather than trying to overwrite the object. S3-compatible services must enforce the signed conditions; support is a deployment prerequisite.

API transfer length is enforced independently of HTTP headers, and SHA-256 is computed while streaming. An expected-checksum mismatch prevents API staging and permits another transfer attempt before expiry. Direct S3 completion reads the object back with bounded streaming and verifies actual size, content type and SHA-256 before staging and publication; ETag or client-supplied metadata is not a substitute for that receipt. Repeated completion uses the persisted verified receipt without rereading bytes.

REST session inspection returns an unavailable transfer descriptor after the direct transfer deadline or after publication, without issuing a fresh presigned URL. The descriptor identifies `expired` or `completed`; it does not prevent authenticated completion of already stored content within the session lifetime.

Completion is idempotent while the published file exists, including after the transfer capability expires. A retry returns the persisted receipt and file identity with current permission and visibility metadata; it cannot restore a deleted file. Legacy sessions without a verified receipt remain compatible with their existing completion interfaces, but the new completion tool does not invent a checksum for them.

## Deployment admission

For local/API capability transfers, an external authentication gateway must admit only PUT to `/api/filesystem/uploads/{upload_id}/transfer` without browser login. The API still validates the capability before consuming content. Do not exempt the uploads namespace or its other methods from normal authentication.

Direct S3 transfers do not require a browser-login exception on the Umbod API. The storage endpoint must be client-reachable and support the signed single-PUT conditions. Browser clients additionally require HTTPS and bucket CORS permitting their frontend origin, PUT, and required headers. See [S3 file-content storage](../operations/s3-file-storage.md#direct-upload-sessions).

The repository's Docker Compose configuration includes this narrow routing exception. Ingress controllers with additional external-auth annotations need an equivalent deployment-specific rule. REST and MCP workers must share durable session persistence and content storage for cross-worker transfer and publication.
