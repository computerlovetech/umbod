---
description: Umbod REST endpoints for personal access tokens and files, and where to find the full OpenAPI contract.
---

# REST API

The REST API is served under `/api`. The administrator contract is at `/api/admin/openapi.json`, and `/api/me/profile` returns the signed-in identity and what it may do.

Clients that are not browsers send `Authorization: Bearer <access token>` from your identity provider. Browser requests that change data must send `X-Umbod-Web-Request: 1`.

## Personal access tokens

A personal access token lets a user's agent send [telemetry](../self-host/telemetry.md). It cannot sign in or do anything else. Users also manage tokens in the workspace under **Access tokens**.

| Method | Path | Does |
| --- | --- | --- |
| `POST` | `/api/me/personal-access-tokens` | Create a token |
| `GET` | `/api/me/personal-access-tokens` | List your tokens, without secrets |
| `DELETE` | `/api/me/personal-access-tokens/{token_id}` | Revoke a token. Takes effect immediately |

Create a token with all three fields:

```json
{
  "name": "laptop",
  "expires_at": "2027-01-31T00:00:00Z",
  "permissions": { "telemetry": "write" }
}
```

| Field | Rule |
| --- | --- |
| `name` | 1 to 256 characters |
| `expires_at` | A future time with a timezone |
| `permissions` | `{"telemetry": "write"}` is the only supported permission |

The response is `201` with `metadata` and the `token`. The token is shown once, so store it right away. Umbod keeps only a hash.

| Status | Meaning |
| --- | --- |
| `422` | Invalid request. Nothing is granted by default |
| `404` | The token does not exist or belongs to someone else |
| `503` | Storage failed. The change was not made |

## Files

Requests act with the signed-in user's permissions. IDs are UUIDs: use the ones the API returns.

| Method | Path | Does |
| --- | --- | --- |
| `POST` | `/api/me/filesystem/home` | Return your personal namespace, creating it if needed |
| `GET` | `/api/me/filesystem/namespaces` | List the namespaces you can access |
| `GET` | `/api/me/filesystem/shared-with-me` | List items shared directly with you |
| `PATCH` | `/api/me/filesystem/nodes/{id}` | Rename, move, or change metadata. Send the current revision in `If-Match` |
| `GET` | `/api/me/filesystem/nodes/{id}/access` | List an item's shares. Returns an `ETag` |
| `PUT` | `/api/me/filesystem/nodes/{id}/access` | Replace an item's shares for `recipient_type=group` or `user`. Send the `ETag` in `If-Match` |
| `GET` | `/api/me/filesystem/nodes/{id}/access/recipients` | Search for groups and users to share with (`query`, optional `recipient_type`) |

Administrators manage shared namespaces:

| Method | Path | Does |
| --- | --- | --- |
| `GET`, `POST` | `/api/admin/filesystem/namespaces` | List and create |
| `PUT` | `/api/admin/filesystem/namespaces/{namespace_id}` | Replace the name and group access. Send `expected_revision` |
| `DELETE` | `/api/admin/filesystem/namespaces/{namespace_id}` | Delete an empty namespace |

On `412` or a revision conflict, read the resource again and reapply your change. Add `?delivery=stream` to a content download to receive the bytes from Umbod instead of a redirect to S3.
