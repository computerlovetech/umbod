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

The client computes the local file's exact byte size and, preferably, its SHA-256 programmatically. Begin accepts the existing parent UUID, filename, metadata, declared size, and an optional lowercase hexadecimal `expected_sha256`. It returns an upload identifier, transfer deadline, and raw HTTP PUT instructions. The public API origin must be configured to an address reachable by the client.

The client streams the original file with the returned headers, without redirect following, cookies, or MCP bearer credentials. File bytes do not belong in either MCP tool call. HTTP uploads use the configured filesystem upload limit; the existing inline tool retains its separate 10 MiB ceiling.

Complete requires the authenticated caller that owns the session. Publication remains private and atomic. The result includes node metadata, the verified byte count, SHA-256, and an MCP resource link. The receipt describes the bytes published by that upload. Resource reads resolve current authorized content and retain their separate 1 MiB limit; larger files require HTTP download.

## Transfer authority

The `X-Umbod-Upload-Token` header is a secret capability for PUT to one upload's exact transfer endpoint. Only its digest is retained. Its lifetime is at most 15 minutes and never exceeds the upload session deadline. It cannot authorize completion, session inspection, downloads, or other filesystem operations.

Transfer admission checks the stored user identity, including issuer, and the group membership delegated at initiation. Current filesystem grants are checked before and after byte transfer. Upstream group-membership changes are not refreshed during this bounded delegation. Completion checks a fresh authenticated caller and current authorization.

Transfer endpoint responses use `Cache-Control: no-store`. Treat the returned transfer instructions as secrets and do not cache them. Credentials must not appear in URLs, logs, diagnostics, or unrelated HTTP requests.

## Retries and verification

Begin is not idempotent. A lost begin response does not justify blindly creating another session.

Only one transfer can claim a session at a time. Failed or interrupted transfers release their matching claim for retry. A successful transfer consumes its capability and cannot be replaced by replaying PUT. A worker crash after a durable claim can leave the upload conflicting; restart recovery of abandoned claims is not provided. Start a new session when that outcome is established rather than claiming the original upload succeeded.

Actual streamed length is enforced independently of HTTP headers. SHA-256 is computed while streaming and retained with the staged content. An expected-checksum mismatch prevents publication and permits another transfer attempt before expiry. Completion does not reread file bytes.

Completion is idempotent while the published file exists, including after the transfer capability expires. A retry returns the persisted receipt and file identity with current permission and visibility metadata; it cannot restore a deleted file. Legacy sessions without a verified receipt remain compatible with their existing completion interfaces, but the new completion tool does not invent a checksum for them.

## Deployment admission

An external authentication gateway must admit only PUT to `/api/filesystem/uploads/{upload_id}/transfer` without browser login. The API still validates the capability before consuming content. Do not exempt the uploads namespace or its other methods from normal authentication.

The repository's Docker Compose configuration includes this narrow routing exception. Ingress controllers with additional external-auth annotations need an equivalent deployment-specific rule. REST and MCP workers must share durable session persistence and content storage for cross-worker transfer and publication.
