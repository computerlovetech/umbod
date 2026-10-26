# Planned filesystem HTTP contracts

This submodule owns design-only operations under authenticated `/api/me/filesystem`. These are not capabilities available to clients. No frontend, content adapter, core policy, persistence migration or storage operation is implemented here.

## Module index

- `routes.py` registers the planned endpoint index, strict UUID/query/header validation and OpenAPI planned markers.
- `models.py` defines boundary-only rename/move/access requests and the fixed 501 error envelope.
- `deps.py` verifies the existing caller snapshot through the injected verified identity resolver and emits the sanitized unavailable response.
- `uploads.py` selects legacy JSON empty creation or rejects planned multipart upload before reading the request body.

The existing filesystem router includes the planned router exactly once. Existing root/node/children/directory routes retain their behavior.

## Current behavior

Every valid planned request returns 501 with `detail.code=filesystem_not_implemented`, `detail.message=Filesystem operation is not implemented.` and `Cache-Control: no-store`. OpenAPI marks these operations `x-umbod-status: planned` and documents the 501 response, not a successful empty result.

Authentication still runs in the mounted user application. Request-local `CallerSnapshot` and `VerifiedIdentityResolver` checks preserve denial of simulated, deployment-only, missing and unresolved identities. Cookie mutation CSRF safeguards remain effective. Invalid UUIDs, scope, revision headers and JSON DTOs return framework validation errors. Identity verification is not item authorization: placeholders never look up items, ownership, grants or content. Existing, inaccessible and missing identifiers therefore produce identical 501 responses for verified callers. No authorization or existence claims can be inferred.

## Endpoint index and intended success contracts

All contracts below are planned, not implemented. No success response schema implies an available capability.

| Method and path | Intended request | Intended response |
| --- | --- | --- |
| GET `/nodes?scope=owned\|shared` | Required scope enum. Owned means caller-owned; shared means accessible non-owned nodes. | 200 safe node-summary page with opaque next cursor. |
| GET `/nodes/{node_id}/breadcrumbs` | UUID identifier. | 200 ordered root-to-node safe summaries, filtered by authorization; never storage paths. |
| GET `/nodes/{node_id}/content` | UUID file identifier. | 200 authorized byte stream with safe content type, disposition and revision ETag; never storage keys. |
| PUT `/nodes/{node_id}/content` | Binary `application/octet-stream` body and If-Match. | 200 updated safe summary and ETag after atomic revision-checked replacement. |
| PATCH `/nodes/{node_id}` | Strict JSON with at least one non-null `name` or UUID `parent_id`, plus If-Match. | 200 updated safe summary and ETag after authorized rename/move. No ownership change contract. |
| DELETE `/nodes/{node_id}` | If-Match; no body. | 204 after authorized revision-checked deletion of a file or empty folder; nonempty folders are rejected. Recursive deletion is not contracted. |
| GET `/nodes/{node_id}/access` | UUID identifier. | 200 authorized owner/direct-grant projection and ETag. Never a fake capabilities map. |
| PUT `/nodes/{node_id}/access` | Strict JSON `grants` list and If-Match. | 200 updated direct-grant projection and ETag. |

PATCH accepts only name and/or parent_id; absent fields mean unchanged and explicit null is rejected. Its nullable types are confined to the raw boundary DTO, never passed to core logic. It cannot inject metadata, owner, caller, grants or content. Access grants contain only a principal (`type=user|group`, nonempty issuer and id), permission list (`discover|read|write|delete|share`) only. Only the access route accepts grants; no route accepts ownership assignment or system principals. Empty direct-grant lists intend explicit replacement, not ownership removal. Inheritance and recursive sharing behavior are not introduced or accepted as request fields. Future core authorization must enforce sharing policy; DTO acceptance currently grants nothing. Future implementation may refine these provisional design contracts.

Mutation If-Match is required and syntactically a quoted positive integer revision. Missing/malformed headers currently return 422. Planned implementation must compare the revision atomically, return 412 for stale revisions and return fresh revision ETags on success. There is no wildcard/unconditional write contract. Current placeholders never compare revisions or inspect state.

Pagination is planned for owned/shared listings and future child browsing: bounded page size and opaque cursor, with a node-summary page and an explicit next-cursor end state. Parameter names, bounds and cursor encoding remain uncommitted. No pagination parameters are supported here; existing `GET /nodes/{parent_id}/children` remains its unchanged unpaginated `nodes` envelope. Clients must not assume ignored query parameters paginate existing children.

## Legacy empty creation and planned upload

`POST /nodes/{parent_id}/files` retains its existing 201 JSON name/metadata empty-file creation for compatibility. This design deprecates that usage; it is not a user-UI creation flow. It remains distinct from upload, and is not marked wholly deprecated in OpenAPI because the same operation also carries the planned upload contract.

The same endpoint documents planned `multipart/form-data` with a required binary `file` part, optional `name` override and optional JSON `metadata` part, with no authority fields. Without overrides, the file part supplies the filename and content type. Its current response is explicitly 501, even for malformed multipart bodies, after caller verification but before body reading, form parsing, persistence preparation or file storage. It never creates an empty node as an upload substitute. Unknown media types remain 422 validation errors; JSON validation retains body-prefixed error locations. Future upload must validate limits and names, authorize the parent and commit content/node state together. Name collisions return 409 rather than overwriting; uploaded items are creator-owned and private. None of this is implemented.

## Future browser capabilities

Item responses are intended to expose server-evaluated `can_download`, `can_upload`, `can_rename`, `can_move`, `can_delete` and `can_share` capabilities. These describe available authorized actions, not permission guesses based on administrator status. They are not implemented or fabricated in current summaries. The first Files UI uses existing browsing and folder creation only; the server authorizes each creation attempt.

No content reads, upload parsing, content replacement, permission evaluation, item lookup or writes are added by planned endpoints.
