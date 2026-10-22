# Personal MCP OAuth provider policy

## Status

Implemented and verified through the API, persistence and provider ports. No real external OAuth account was used. The original iteration excluded personal runtime execution; subsequent runtime and user recovery delivery is recorded in the authorization specification. Administrator allowlist UI delivery is implemented and verified below.

## Scope

Extend durable personal authorization with administrator-approved requested scopes and preconfigured public/confidential clients. Preserve automatic availability, administrator publication and grants, explicit user enablement and consent, shared authentication, Desktop removal and unrelated changes. Runtime execution, discovery, refresh, UI, confidential dynamic registration, client metadata documents, JWT client authentication and providers without the current S256/issuer-binding profile remain outside this iteration.

## Decisions and contracts

The existing downstream MCP context owns the policy; `personal_oauth_configuration/` groups its pure models and store port. Definitions remain secret-free and unchanged. An additive encrypted configuration record holds the complete policy, with connector identity and a nonsecret revision bound into the encrypted document. Missing records resolve to revision `legacy`, empty requested scopes and dynamic public registration. Existing normalized definition hashes must not change, and old durable preparations/contexts receive compatible legacy defaults.

`PersonalOAuthSettings` contains `requested_scopes` and an explicit client variant: `dynamic_public`, `preconfigured_public`, or `preconfigured_confidential`. Static clients require an administrator-configured exact HTTPS `issuer_url` and `client_id`; confidential clients additionally require `client_secret` and an explicit `client_secret_basic` or `client_secret_post` method. Discovery must advertise that configured issuer before using the static client. Configured client credentials identify Umbod's OAuth application, not an administrator's downstream user account; user grants and tokens remain principal-scoped. Never send an administrator-configured client secret to an issuer chosen solely by a resource's mutable metadata. Preserve exact issuer spelling and all existing destination, resource, redirect and PKCE checks.

Scopes use OAuth scope-token syntax, are case-sensitive, unique and canonicalized by sorting. Bound at 64 tokens, 256 ASCII characters per token and 4,096 characters space-joined. Request the exact administrator-configured set, without inference or expansion from metadata. AS scope advertisements are optional and may be incomplete even when supplied; they do not veto an explicit administrator request or establish consent. An explicit dynamic-registration scope response must equal the requested set; omission is accepted without interpreting it as a token grant. Empty requested sets omit scope parameters and retain the documented implicit-provider-default limitation.

Token scopes may narrow but may not exceed requested scopes. Omitted token scope is interpreted as the requested set under RFC 6749; explicit empty scope is an empty grant. Save requested/effective granted scope sets and configuration revision alongside authorization. Callback scopes are optional validation-only data: reject malformed or excessive scopes, but do not treat them as final grants. No automatic step-up requests occur.

Preconfigured clients never register dynamically, require no registration endpoint, and never fall back on failure. AS authentication-method metadata defaults to `client_secret_basic` when absent; dynamic-registration authentication defaults likewise. Dynamic public registration still requires `none`. Static clients must use their explicitly configured method, supported by metadata. Preserve code/S256 support and issuer-bearing callbacks. Static client-secret expiry is provider/operator-managed in this iteration: provider rejection fails safely without retries, fallback or installation; no unknown expiry is invented.

OAuth Basic authentication UTF-8 form-encodes identifier and secret separately before colon joining and Base64 encoding. Send Basic credentials only through a typed, secret-bearing Authorization field at the transport boundary. POST authentication sends credentials only in the form body. Public clients send no secret. Never put secrets in URLs, authorization requests, diagnostics, definition JSON or projections. Store secrets only under the configured encryption root; the public administrator boundary rejects confidential writes without a nonblank root-derived configuration secret.

## Administrator boundary

Extend `POST /api/admin/connectors/mcp/personal-oauth` with optional `configuration.oauth_configuration`, preserving endpoint-only creation as empty-scope dynamic public registration. Map this to `CreatePersonalOAuthConnectorDefinition.oauth_configuration`. Create definition and configuration atomically, without network I/O, shared credentials, health, catalogue, publication or activation.

Add authenticated `GET` and `PUT /api/admin/connectors/mcp/{connector_id}/personal-oauth`. GET projects connector ID, policy revision, requested scopes and nonsecret client fields; confidential projections expose only `client_secret_configured=true`, never plaintext, ciphertext or masked placeholders. PUT accepts `expected_revision` and complete `settings`. The public route maps these into `ReplacePersonalOAuthConfiguration`; it is full replacement, not PATCH: confidential settings must explicitly supply a nonblank replacement secret. Omission is not implicit retention. Generic personal metadata/configuration edits remain blocked. Existing authentication and cookie-CSRF controls apply.

All validation errors on these personal administrator writes must be sanitized, including unknown fields, malformed discriminators and unrelated invalid fields in bodies containing secrets. Do not reflect Pydantic input dictionaries or submitted credentials. Existing shared endpoint validation behavior remains unchanged.

Configuration replacement is optimistic and serialized. Reject stale revision or non-personal/missing definitions without mutation. A public/dynamic policy unchanged after canonicalization is a no-op; a supplied confidential secret is explicit rotation even if equal to the old value. Every effective change receives a new revision and atomically removes all personal authorizations, changes connection revisions while preserving enablement, erases all connector attempts and replaces obsolete configured secrets. Completed-attempt history may be removed during policy change. No remote token revocation is claimed. Preserve publication, grants and other connector metadata.

## Durable workflow

`PreparePersonalOAuth.policy` snapshots the resolved revision/settings, including any configured secret, inside encrypted attempt storage. The owner service loads current configuration after identity/eligibility checks and before reservation. Reservation, publication, claim and completion recheck exact current policy against this snapshot inside their existing serialized transaction. Provider context binds policy revision, scopes, registration/client method and static client identity; exchange uses the captured preparation without rediscovery or registration replay. Old legacy preparations remain valid only for unchanged legacy configuration.

Deletion removes encrypted configuration in the existing aggregate transaction. Configuration changes and completion serialize against each other: if completion wins, configuration update removes its authorization; if update wins, the old attempt cannot install anything. Wrong-owner/state/claim protections, immediate expiry erasure, final-time expiry rechecks and one-shot exchange remain unchanged.

## Acceptance

- Given an old personal definition and old durable context, when no configuration exists, legacy behavior and hashes remain unchanged.
- Given valid configured scopes and absent/incomplete advertisements, authorization requests only that exact set; invalid, duplicate or oversized inputs fail before mutation.
- Given narrower, omitted, empty or excessive returned scopes, the recorded grant follows the explicit rules above; excess never installs authorization.
- Given any static client, preparation and resumed exchange perform no registration; configured issuer mismatches fail before secret use.
- Given each supported authentication method, only its one intended credential location is used, including reserved and Unicode Basic credentials.
- Given any malformed administrator request containing sentinel secrets, errors, projections and logs contain none of those secrets.
- Given persistent storage and recreated adapters, secrets decrypt correctly only under the correct connector/revision binding and remain absent from definition JSON and raw encrypted rows.
- Given concurrent policy edits, stale expected revisions cannot overwrite the newer policy.
- Given an active preparation/exchange or existing authorization, replacement erases old secrets and attempts, preserves user enablement, and prevents all stale completions.
- Given injected mutation failure, configuration, connections, attempts and aggregate creation/deletion roll back together.
- Given deletion followed by late work, neither configuration nor authorization can resurrect.
- Given user initiation with scope/client/owner overrides, the strict empty-object request still rejects it.
- Given successful personal authorization, shared credentials remain untouched and runtime availability stays false.

## Verification

Run policy and persistence contracts through in-memory and SQLite database adapters, provider transport fixtures, service and REST boundary tests, full API/MCP regression, Ruff and shared Semgrep. Verify the running services in disposable Kind, including policy read/replace, safe secret projections, invalid-secret responses, opt-in and existing runtime guards. No real external account is available: protocol fixtures and live negative/administration checks are not an interoperability claim. Published Helm and frontend are unchanged. Operator ingress callback exemptions and query-redaction obligations remain. Secret-bearing administrator bodies and token Authorization headers must also be suppressed or redacted by proxies, tracing and error reporters.

Verified: 2,819 API/MCP tests passed, two existing parametrization skips; Ruff and `git diff --check` passed. Disposable Kind installation and all 29 live runtime tests passed, including confidential creation, safe policy projections and replacement, stale-write rejection, validation/CSRF secret checks, private-provider denial and collected API stdout secret sentinels. The initial Kind run incorrectly assumed its development administrator simulation rejected anonymous access; that assertion was corrected to verify the independently authenticated personal-user boundary instead. Shared Semgrep remains at the prior 52 findings with no new findings. Positive protocol flows use controlled transports and include recreated-worker completion for all supported client methods, exact Basic encoding, narrowed/omitted scopes and policy changes during an active exchange.

## Administrator allowlist UI delivery

The centrally managed inventory of personal MCP definitions is the global server allowlist; it is not universal user access or a second authorization mechanism. Add `/admin/personal-mcp-servers`, labelled Personal MCP servers in Admin navigation and linked from the shared MCP proxy workspace. The shared proxy workspace excludes personal definitions and must not load their shared discovery, credentials, prompts, resources or tool bundles. Ownership is required in validated response contracts; missing or invalid `authorization_mode` fails closed, never defaults to shared.

The page supports registration, reading and replacing OAuth settings, explicit publication/withdrawal, and confirmed deletion through existing administrator APIs. Registration uses `POST /api/admin/connectors/mcp/personal-oauth` and starts unpublished, with no discovery, group grants, owner enablement or consent. OAuth policy reads and revision-checked replacements use `GET`/`PUT /api/admin/connectors/mcp/{id}/personal-oauth`. Publication uses bodyless `PUT`/`DELETE /api/admin/connectors/mcp/{id}/publication`; deletion uses the existing connector DELETE. Server name, endpoint, prefix and public path are read-only after registration because generic personal definition edits are unsupported.

Provide dynamic public, preconfigured public and preconfigured confidential client forms, explicit Basic/POST confidential authentication, and bounded canonical scopes. Use separate validated request and nonsecret response schemas. Confidential reads only display configured status; every confidential write requires a newly entered secret. Secrets remain transient, never populate a response, URL, browser storage or diagnostics, and are cleared on submission, failure, close, disposal and client-kind changes. Before replacing settings, require confirmation explaining that an effective policy change removes all users' saved authorizations and pending sign-ins without remote token revocation. Preserve publication, group grants and user enablement.

Use a typed administration port, in-memory adapter, validated HTTP route adapter and the existing composite client/transport. UI state is scoped to the component lifecycle, with explicit actions and stale-result/disposal guards. Render fixed safe errors, never raw provider bodies or schema issues. A configuration conflict requires an explicit authoritative reload; uncertain writes must not be automatically repeated. After an uncertain outcome, block further mutations until explicit reload reconciles server state. Authentication loss clears loaded administration state and secrets without automatic navigation. Unavailable deployments report that limitation rather than offering a credential fallback.

Publication permits selection by explicitly granted groups, not all users. Include a Group permissions link and persistent guidance that approved tool contracts, activation and tool permissions remain separate prerequisites for execution. Personal definitions can be published and selected without approved tools; never label that state ready to execute. Full approved-tool contract editing remains API-only in this slice. No owner OAuth action, automatic discovery, permission grant or operation replay is introduced.

### Administrator UI acceptance

- Given a new personal server, when registration succeeds, then it remains unpublished and no provider or discovery request, group grant or owner action is issued.
- Given any supported client kind, when valid settings are submitted, then the exact issuer/client method and canonical requested scopes are sent; invalid scopes or secret-bearing settings fail safely before I/O.
- Given a confidential configuration, when it is read or edited, then no stored secret is returned or prefilled, and saving requires a fresh secret that is cleared after the attempt.
- Given an existing policy, when the administrator saves an edit, then explicit invalidation confirmation precedes exactly one revision-checked replacement.
- Given a stale revision or uncertain result, when the error is shown, then no mutation is repeated and an explicit reload is required before another write.
- Given navigation, disposal or authentication loss during a request, when an older response arrives, then it cannot restore stale records or secrets.
- Given an unpublished server without approved tools, when publication succeeds, then Published is shown without an execution-readiness claim; only explicitly permitted groups can select it.
- Given withdrawal, when the user catalogue is reloaded, then new selection eligibility is revoked without implying token revocation or owner disconnect.
- Given an outstanding connector/tool grant, when deletion is rejected, then the UI explains the need to remove grants and does not retry deletion.
- Given saved grants for an unpublished or otherwise unassignable connector, when Group permissions is opened, then those grants remain visible for removal. Removal is staged and saved explicitly through disabled permission changes without republishing, adding grants or changing unrelated permissions. The server detail exposes its ID for matching retained grants.
- Given personal rows or missing ownership in an MCP list response, when the shared workspace loads, then personal rows are excluded and malformed ownership fails safely before shared bundle requests.

Verify frontend contract/state/component tests, Bun/Svelte checks, shared Semgrep and whitespace checks. Rebuild Compose and exercise the real UI at `http://localhost:3010` using isolated disposable data for administrator CRUD, publication/withdrawal, confidential secret projection and shared-workspace isolation. Inspect mobile layout, console/page errors and saved screenshots. Controlled browser fault injection may cover conflict/uncertainty/authentication-loss branches but must be reported separately from running-service verification. No backend or Helm changes are planned; if that scope changes, run their mandatory runtime gates.

Verified administrator UI delivery: 631 frontend tests passed; Svelte checks reported zero errors and one existing administration accessibility warning. Shared Semgrep completed with the unchanged 66 findings, and whitespace checks passed. Independent reviews identified native-validation secret retention, modal focus handling and a long-label mobile overflow; all were corrected with regression coverage. The rebuilt Compose UI was exercised at localhost:3010 with isolated disposable data: registration stayed unpublished, explicit publication worked without approved tools, confidential POST-client settings were saved and read back without a secret, shared-workspace direct selection excluded the personal server, and outstanding grants blocked deletion with safe guidance. After withdrawal, saved grants were explicitly removed through Group permissions without republishing; deletion then succeeded. Native invalid submissions cleared secrets without writes; modal keyboard isolation, Escape cancellation and opener/fallback focus were checked, together with desktop/mobile layouts and verified screenshots. Controlled fetch faults separately verified conflict blocking, a lost response after a real committed policy update, manual reconciliation without replay, and state clearing on 401 without navigation. Browser console/page errors and service-stdout credential sentinels were clear. No provider discovery or shared execution endpoint was called for the personal fixture. Test data was removed and the default Compose configuration restored. These checks used local administrator simulation and do not establish external-provider account interoperability or authenticated user-catalogue interoperability.

## References

- RFC 6749 sections 2.3.1, 3.3 and 5.1: client authentication and scope semantics.
- RFC 8414 section 2: optional/incomplete scope advertisements and authentication defaults.
- RFC 7591 sections 2 and 3.2.1: dynamic registration metadata and response validation.
- MCP 2025-11-25 authorization: pre-registration, protected-resource discovery, S256 and resource indicators.
