---
type: API Contract
title: Personal access tokens
description: Authenticated issuance and management of opaque personal tokens with explicit resource permissions.
---

# Personal access tokens

Have users create, list, and revoke their own tokens while signed in. A personal access token cannot sign a user in or manage other tokens. The only supported grant is `telemetry` at level `write`, for sending data to the collector. Users must request that permission and enter an expiry; Umbod grants nothing by default. Save the secret when it is issued, and revoke the token if it is no longer needed or may have been exposed.

## Endpoints

| Method | Path | Behavior |
| --- | --- | --- |
| POST | /api/me/personal-access-tokens | Issue a token with explicit permissions and expiry |
| GET | /api/me/personal-access-tokens | List all tokens owned by the authenticated user |
| DELETE | /api/me/personal-access-tokens/{token_id} | Delete an owned token and invalidate its credential |

Use the authenticated user's sign-in identity. In production and by default, the issuer and subject must be verified upstream. Writes carrying a cookie require a trusted Origin and `X-Umbod-Web-Request: 1`.

For local development, token management allows the server-established simulated user only when all of the following are set: `runtime.profile=local`, `runtime.auth=dev`, administrator authentication mode `simulation`, environment `development`, and a nonblank configured simulated user ID. The issuer must be exactly `urn:umbod:local` and the subject must exactly match that ID. This user uses the same create, list, and revoke endpoints without a separate login form. Umbod does not treat simulated identities as verified; all other simulated, semantic, test, unavailable, and deployment identities remain denied.

## Creation contract

Creation requires all of these fields:

| Field | Meaning |
| --- | --- |
| name | Nonblank label, at most 256 characters |
| expires_at | Explicit timezone-aware expiry in the future |
| permissions | Nonempty mapping of supported resource names to permission levels |

Request only supported resource names and permission levels. The server determines the owner, audience, and scopes. Clients cannot supply those directly, specify URLs or HTTP methods, or use wildcards. Invalid requests return 422; Umbod never substitutes a broader or default grant.

The supported grant is:

| Resource | Level | Effective audience | Effective scope | Permitted operations |
| --- | --- | --- | --- | --- |
| telemetry | write | umbod:telemetry | telemetry:write | POST /v1/logs, /v1/metrics and /v1/traces on the collector |

Telemetry read, analytics, administration and MCP permissions are not supported. Adding another supported resource requires an explicit server-side access rule, authorization that the issuing user may grant it, and enforcement by that resource's endpoint. Catalogue membership alone must not confer a future privileged permission; telemetry ingestion is currently available to every upstream-verified user and the explicitly configured local development user described above. A token does not authenticate a normal sign-in merely because it has been issued by Umbod.

The permission selection follows the resource-permission approach of [GitHub fine-grained personal access tokens](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens). Umbod's creation route is its own API contract, not a copy of a GitHub token-creation endpoint.

## Responses and lifecycle

Successful creation returns 201 with `metadata` and the plaintext `token`. Metadata records the effective audience and scopes, owner, token ID, label, creation time, expiry and status. Audience and scopes are the canonical persisted access representation; there is no second independently mutable permission record.

Store the secret securely at issuance; Umbod does not return it again. Listing shows metadata for all owned tokens across all audiences, without secrets or hashes. Revoke a token to permanently delete its stored hash and metadata. A successful revocation returns 204, and the token no longer appears in listings or passes verification. Missing, already deleted, and other users' IDs all return the same 404. Legacy revoked records can still be read and deleted through the same endpoint.

Use the general management endpoint for existing telemetry tokens. The old telemetry-specific route has no alias or redirect, but previously issued tokens remain verifiable with the same hashes, audiences, and scopes.

Management responses are not cacheable. Required storage failures return sanitized 503 responses; failed writes are never acknowledged as successful. Tokens expire at the recorded instant and revocation is authoritative on subsequent verification requests, without a cross-request authorization cache.

## Storage and verification

Keep the bearer token in a local secret store. This API does not implement a Rust client or platform adapters. Umbod stores only SHA-256 token hashes and metadata. Tokens contain 256 bits of cryptographically secure random secret material. Verification uses a public token ID primary-key lookup, constant-time hash comparison, and audience, scope, expiry and revocation checks.

The existing backend-neutral Database interface and its in-memory and SQLite drivers provide persistence. Business-logic tests use the in-memory driver; low-level SQLite tests cover durability and cross-runtime revocation.

Local development issues real random tokens through the same service and stores their hashes in the same owner-scoped registry. They authenticate the API-hosted collector normally and stop working immediately after revocation; they are not placeholder credentials or sign-in tokens. The collector rejects tokens whose owner issuer is `urn:umbod:local` unless the full local-development configuration gate remains enabled. Reusing that database after switching to production therefore does not make local tokens valid production ingestion credentials. Custom embedding must explicitly supply application settings when installing the token verifier. Composition enables this local namespace only through the full configuration gate. Core token validation remains transport-neutral and checks credential validity; the collector applies this deployment restriction separately.

The API-hosted collector shares the authoritative application persistence runtime with token management. The independent collector process does not implicitly acquire that registry. See [telemetry ingestion](./telemetry-ingestion.md) for listener configuration, standalone limitations, legacy shared-bearer compatibility and analytics ownership.
