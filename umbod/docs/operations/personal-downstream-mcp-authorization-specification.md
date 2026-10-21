# Durable personal downstream MCP authorization

## Status

Implemented and verified. Personal selection and authorization default to automatic availability once their security prerequisites are configured; administrators can explicitly opt out. No frontend, personal runtime execution or published Helm chart changes are included.

## Scope

Third main-Umbod iteration: durable owner-scoped authorization attempts and worker-independent callbacks. Preserve Desktop removal, shared authentication and unrelated changes. Runtime execution, discovery, refresh scheduling and frontend remain disabled. Expose authorization automatically when the explicit identity namespace, validated authentication policy, persistent SQLite and a nonblank encryption secret are configured. Both operator feature modes default to `auto` and accept explicit `true`/`false` overrides. Missing prerequisites keep automatic availability off; explicit invalid enablement and malformed supplied identity configuration still fail startup. Direct embedded application configuration retains resolved boolean fields. Automatic deployment availability does not change administrator approval, per-user enablement or OAuth consent. Supported worker-independent topology uses a shared persistent database file, identical encryption configuration and SQLite-compatible locking/storage semantics; separate pod-local databases are unsupported. SQLite remains a development/evaluation backend, not a new production database architecture.

## Provider support

Support RFC 9728 protected-resource metadata, RFC 8414 issuer metadata, authorization code with S256 PKCE, RFC 9207 issuer-bearing responses, and dynamic public-client registration with authentication method `none`. Require exact issuer/resource/client/redirect binding. Include RFC 8707 `resource` with the exact validated protected-resource identifier in authorization and token requests. Reject endpoint query parameters that could override protocol or scope parameters. Use the configured public API origin plus `/api/oauth/downstream-mcp/callback`; never derive callback URLs from request headers. Unsupported providers fail explicitly without shared credentials, historical client metadata, preconfigured/confidential-client fallback or inferred scopes.

Approved requested scopes are empty in this iteration. Omit scopes from requests; reject nonempty scopes in registration, callback and token responses. This is not a zero-privilege guarantee: providers may assign implicit defaults. The subsequent [provider-policy iteration](personal-downstream-mcp-provider-policy-specification.md) supersedes this initial subset with explicit requested scopes and pinned preconfigured public/confidential clients; it preserves all durable ownership and one-shot guarantees.

All provider requests require TLS verification, connection-time public-address validation and pinning, no redirects/proxies, bounded timeouts and response bodies, and no automatic ambiguous POST retries. Do not connect to MCP or enumerate capabilities during authorization.

## Contracts

Domain models and ports live in `personal_connections/oauth_models.py` and `oauth_ports.py`. Reserve a `preparing` attempt before outbound discovery/registration, then publish prepared context as `pending` before returning its authorization URL. Require an existing enabled personal connection and current connector-level grant/publication. One active attempt per owner/connector; concurrent starts conflict.

Persist owner key, expected connection revision, definition fingerprint, verified group snapshot, expiration, PKCE verifier, opaque unpredictable state and validated provider/client context encrypted. Only attempt identifier/status/expiry and the initiating owner's authorization URL may leave these boundaries. Terminal attempts erase sensitive preparation/context. Bound retained history per owner/connector; expire interrupted preparation/exchange without replaying authorization codes.

State has an opaque attempt identifier plus an unpredictable secret. A valid callback atomically claims `pending` as `exchanging`. Invalid state, duplicates, expiration and wrong owner queries cannot consume or disclose another attempt. No network request occurs inside a database transaction. Successful completion installs authorization and marks success atomically, checking the claim, expiry, current enabled connection revision, definition fingerprint, personal mode, current publication and current explicit grants against the initiating verified group snapshot. This does not claim live identity-provider group introspection after the initiating JWT was verified.

Cancellation preserves previous authorization and prevents in-flight preparation/exchange from publishing or installing results. Disconnect/disable revision changes invalidate pending completion. Aggregate connector deletion cleans attempts transactionally and prevents resurrection. Unknown exchange outcomes fail closed and require a new attempt; do not replay codes after worker failure.

## REST

- `POST /api/me/connectors/mcp/{id}/oauth/attempts`: strict empty body, return 201 only after durable preparation.
- `GET /api/me/connectors/mcp/{id}/oauth/attempts/{attempt_id}`: owner-scoped safe status.
- `DELETE /api/me/connectors/mcp/{id}/oauth/attempts/{attempt_id}`: owner-scoped cancellation, including cleanup after eligibility withdrawal.
- `GET /api/oauth/downstream-mcp/callback`: unauthenticated but state-bound, fixed secret-free no-store response. Reject duplicate/unknown callback parameters, invalid issuer and malformed or unapproved scope. The initial iteration rejected all nonempty scopes; the provider-policy extension validates them against the captured administrator policy. Never redirect to a supplied return URL.

Existing authenticated user and cookie-CSRF boundaries apply to initiation/cancellation. Callback processing must redact query secrets before access logging; responses must not echo codes, state, provider errors or endpoint details. Error codes distinguish unsupported provider, temporary provider failure, conflict and unavailable attempts without exposing raw exceptions. Catalogue runtime availability remains false even after authorization. Operators must expose this callback without gateway authentication and configure query-free callback logging/redaction at ingress, reverse proxies, tracing and error reporters as well: application middleware cannot redact requests logged before reaching Umbod. No-referrer responses prevent onward browser referrer leakage.

## Acceptance

- A worker starts, adapters are recreated, and another worker finishes with only durable state.
- Same display identity on different principals cannot read/cancel/finish each other's attempts.
- Duplicate callbacks exchange at most once, including independently created concurrent adapters.
- Cancel/expire/disconnect/disable/delete/unpublish/revoke grants during preparation or exchange prevents authorization installation.
- Existing authorization survives failed/cancelled reauthorization.
- DNS rebinding/private and mapped addresses, redirects, mismatched metadata issuer/resource, invalid client registration, unsupported PKCE/issuer responses, and extra returned scopes fail closed.
- Stored data is encrypted and decrypted ownership is validated; projections/logs omit secrets.
- Shared flows and personal runtime guards remain unchanged.

## Verification

Verified: 2,733 API/MCP tests passed, two skips (existing empty Desktop-path parametrization and one SQLite-only contract case under the in-memory parametrization); Ruff and `git diff --check` passed. Disposable Kind installation/chart tests and all 26 live runtime tests passed, including private-provider denial, public callback rejection and collected API stdout sentinel checks for callback secrets and the disposable encryption root. Initial authorization verification correctly rejected a Kind fixture without an encryption root; the runner creates a disposable secret shared by the test services. The default-policy follow-up runs Kind without either feature-enabling flag, supplying only the stable test identity namespace and storage/security prerequisites to both services. Configuration tests verify automatic availability, explicit opt-outs and invalid explicit enablement. Compose configuration checks verify consistent mode, namespace and optional SQLite-path forwarding for API and MCP.

Shared Semgrep completed with 52 findings: the prior 47 plus five reviewed nullable parameters required by the httpcore network-backend interface. These SDK-boundary annotations are documented in the adapter index; no rules were suppressed and no additional error-severity findings remain. Review identified expiry cleanup rollback, expiry crossing validation and temporary metadata-outage classification issues; fixes include immediate persisted-secret assertions and controlled-clock tests. Independent focused authorization review verified all fixes with 404 tests passed and one SQLite-specific skip. Default-policy review found no concrete issues and passed 69 focused tests; Semgrep remains unchanged at 52 findings.

Positive authorization flows are verified through provider/store ports and recreated application/adapters, not a real external OAuth account. Running-service checks deliberately contact no real account and reject a loopback provider before connection. External ingress/tracing redaction and each real provider's advertised supported contract remain deployment verification obligations. No Desktop or frontend verification applies to this iteration.
