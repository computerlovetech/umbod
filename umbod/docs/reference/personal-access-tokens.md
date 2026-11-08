---
type: API Contract
title: Personal access tokens
description: Authenticated issuance and management of opaque personal tokens with explicit resource permissions.
---

# Personal access tokens

Personal access token management belongs to the authenticated user's API, independently of the feature that consumes a token. Requested resource permissions determine its access. There is no default permission grant.

## Endpoints

| Method | Path | Behavior |
| --- | --- | --- |
| POST | /api/me/personal-access-tokens | Issue a token with explicit permissions and expiry |
| GET | /api/me/personal-access-tokens | List all tokens owned by the authenticated user |
| DELETE | /api/me/personal-access-tokens/{token_id} | Delete an owned token and invalidate its credential |

These endpoints require the authenticated user's sign-in identity, not a personal access token. Management requires an upstream-verified issuer and subject by default, including in production. Only explicitly configured local development (`runtime.profile=local`, `runtime.auth=dev`, administrator authentication mode `simulation`, environment `development`, and a nonblank configured simulated user ID) also permits the server-established simulated user. Its issuer must be exactly `urn:umbod:local` and its subject must exactly match that configured ID. Other simulated, semantic, test, unavailable and deployment identities remain denied; provenance is never relabeled as verified. The local workspace uses the same create, list and revoke endpoints as ordinary users, without a separate login form. Cookie-bearing mutations require a trusted Origin and `X-Umbod-Web-Request: 1`.

## Creation contract

Creation requires all of these fields:

| Field | Meaning |
| --- | --- |
| name | Nonblank label, at most 256 characters |
| expires_at | Explicit timezone-aware expiry in the future |
| permissions | Nonempty mapping of supported resource names to permission levels |

The server resolves requested permissions through its supported access catalogue. Clients cannot supply an owner, raw audience, raw scopes, endpoint URLs, HTTP methods, wildcard grants or unsupported permission names or levels. Invalid requests return 422 rather than receiving broader or default access.

The initial supported grant is:

| Resource | Level | Effective audience | Effective scope | Permitted operations |
| --- | --- | --- | --- | --- |
| telemetry | write | umbod:telemetry | telemetry:write | POST /v1/logs, /v1/metrics and /v1/traces on the collector |

Telemetry read, analytics, administration and MCP permissions are not supported. Adding another supported resource requires an explicit server-side access rule, authorization that the issuing user may grant it, and enforcement by that resource's endpoint. Catalogue membership alone must not confer a future privileged permission; telemetry ingestion is currently available to every upstream-verified user and the explicitly configured local development user described above. A token does not authenticate a normal sign-in merely because it has been issued by Umbod.

The permission selection follows the resource-permission approach of [GitHub fine-grained personal access tokens](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens). Umbod's creation route is its own API contract, not a copy of a GitHub token-creation endpoint.

## Responses and lifecycle

Successful creation returns 201 with `metadata` and the plaintext `token`. Metadata records the effective audience and scopes, owner, token ID, label, creation time, expiry and status. Audience and scopes are the canonical persisted access representation; there is no second independently mutable permission record.

The secret is returned only during issuance. Listing returns metadata without secrets or hashes and does not filter out owned records by audience. Revocation permanently deletes the owned token's stored hash and metadata and returns 204. Deleted tokens no longer appear in listings or pass verification. Missing, previously deleted and foreign IDs return the same 404 response. Legacy records with a revoked status remain readable and can be deleted through the same endpoint. The old telemetry-specific management route is not retained as an alias or redirect. Existing token hashes, audiences and scopes are unchanged, so previously issued telemetry tokens remain verifiable.

Management responses are not cacheable. Required storage failures return sanitized 503 responses; failed writes are never acknowledged as successful. Tokens expire at the recorded instant and revocation is authoritative on subsequent verification requests, without a cross-request authorization cache.

## Storage and verification

Clients should retain the actual bearer token in a local secret store; the Rust client and platform adapters are not implemented by this API. Backend application persistence retains only SHA-256 token hashes and metadata. Tokens contain 256 bits of cryptographically secure random secret material. Verification uses a public token ID primary-key lookup, constant-time hash comparison, and audience, scope, expiry and revocation checks.

The existing backend-neutral Database interface and its in-memory and SQLite drivers provide persistence. Business-logic tests use the in-memory driver; low-level SQLite tests cover durability and cross-runtime revocation.

Local development issues real random tokens through the same service and stores their hashes in the same owner-scoped registry. They authenticate the API-hosted collector normally and stop working immediately after revocation; they are not placeholder credentials or sign-in tokens. The collector rejects tokens whose owner issuer is `urn:umbod:local` unless the full local-development configuration gate remains enabled. Reusing that database after switching to production therefore does not make local tokens valid production ingestion credentials. Custom embedding must explicitly supply application settings when installing the token verifier. Composition enables this local namespace only through the full configuration gate. Core token validation remains transport-neutral and checks credential validity; the collector applies this deployment restriction separately.

The API-hosted collector shares the authoritative application persistence runtime with token management. The independent collector process does not implicitly acquire that registry. See [telemetry ingestion](./telemetry-ingestion.md) for listener configuration, standalone limitations, legacy shared-bearer compatibility and analytics ownership.
