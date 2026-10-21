# Resumable personal OAuth provider

- `factory.py`: request-scoped authorization and refresh provider lifetimes over the production transport.
- `provider.py`: protected-resource and issuer discovery, public registration or pinned preconfigured-client selection, scoped S256 authorization preparation, and bound one-shot token exchange.
- `refresh.py`: one-shot exchange of a stored refresh token for preconfigured clients, bound to the existing issuer, resource, client and approved configuration. Returned scopes may only narrow the previous granted set; omitted scope and refresh-token fields preserve their previous values only after definite success. New access-token expiry is required. Fixed denied/uncertain outcomes reveal no provider payloads.
- `refresh_logging.py`: context-local suppression of HTTP networking diagnostics during refresh, including unsafe reflected headers. The filter leaves unrelated request contexts unchanged.
- `validation.py`: strict supported wire models, durable provider context, URL and public-address validation, and bounded duplicate-safe JSON parsing.
- `transport.py`: validated HTTP port bundles and the in-memory adapter.
- `network.py`: TLS-verified, redirect-free bounded HTTP and connection-time DNS validation with literal-address pinning.

Supported clients are dynamic public registration, preconfigured public clients and preconfigured confidential clients using explicit `client_secret_basic` or `client_secret_post`. Configured clients pin the administrator-selected issuer and never register or fall back. Missing server authentication-method metadata defaults to Basic. S256 and issuer-bearing callbacks remain required.

Requested scopes come only from administrator policy; optional or incomplete metadata advertisements do not expand or veto them. Registration scope responses, when supplied, must match the request. Token grants may narrow but never expand requested scopes; omitted token scope means the requested set. Empty policy still cannot guarantee zero implicit provider privileges. Effective scope sets and configuration revision accompany persisted authorization. Basic credentials are separately UTF-8 form-encoded before Base64 and sent only through the typed secret header; POST credentials stay in the form body.

Provider context is opaque secret JSON. The personal OAuth attempt store encrypts that context and the preparation before persistence. A recreated provider exchanges using only the claimed attempt, without discovery or registration replay.

Authorization endpoint DNS is validated before returning a browser URL. Server connections resolve and validate again at connection time; browser navigation is outside server connection pinning.

The network backend intentionally mirrors httpcore's nullable timeout, local-address and socket-option parameters. These five boundary annotations are reviewed Semgrep design warnings, not optional domain states; they remain confined to SDK integration. Production requests supply explicit bounded timeouts, and whole-operation deadlines also cover preparation and exchange.
