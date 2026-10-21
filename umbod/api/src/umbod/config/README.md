# Configuration

**Module responsibility:** Typed operator settings, defaults, validation, derivation, and conversion into application configuration.

**Read when working with:** Environment variables, configuration profiles, defaults, secrets, validation rules, or runtime settings consumed by services.

## Modules

### `operator.py`

**Read when working with:** Operator-facing settings and environment-backed configuration.

### `derive.py`

**Read when working with:** Loading operator settings, validation orchestration, or redacted configuration results.

### `build.py`

**Read when working with:** Building internal application configuration from operator settings.

OIDC issuer derivation preserves an explicit `UMBOD_OIDC_ISSUER_URL`. Otherwise Auth0 derives `https://{UMBOD_OIDC_DOMAIN}/`, with the trailing slash matching its discovery issuer. A custom discovery URL without an Auth0 domain requires an explicit issuer in production. Entra and Google require an explicit production issuer: tenant/token-version and issuer spelling must match the JWT exactly, rather than being guessed from the provider recipe. All production OIDC recipes require `UMBOD_OIDC_AUDIENCE`; missing audience or an issuer that cannot be derived is rejected during operator configuration validation. Local authentication modes are unchanged.

### `secret_derivation.py`

**Read when working with:** Secret generation and resolution.

### `app.py`

**Read when working with:** Internal application configuration consumed at runtime, including `user_profile` mapping and token-role validation, and the independently enabled OTLP receiver and its request limit. Operator OTLP bearer credentials are excluded from configuration inspection and redacted display.

### `validate.py`

**Read when working with:** Cross-field configuration constraints and startup validation. Optional profile mode, header and mapping settings are assembled explicitly in `build.py`, validated by `validate.py` and `app.py`, and exposed through the non-secret inspection catalog. The [environment reference](../../../../docs/operations/configuration.md#optional-user-profile-enrichment) defines the profile contract.

### `personal_connection_policy.py`

**Read when working with:** Resolving automatic personal selection and OAuth modes into runtime booleans.

### Personal connections identity policy

Operator settings `UMBOD_PERSONAL_CONNECTIONS_ENABLED` and `UMBOD_PERSONAL_CONNECTIONS_OAUTH_ENABLED` default to `auto` and also accept explicit `true` or `false`. Automatic selection activates when `UMBOD_PERSONAL_CONNECTIONS_IDENTITY_NAMESPACE` is supplied; the namespace is never generated or derived. Supplied whitespace or malformed namespaces are validated, not silently disabled. Without a namespace, the unconfigured development deployment keeps both features unavailable. Explicit `false` opts out. Direct embedded `AppConfig.personal_connections` construction retains conservative disabled boolean defaults; operator assembly always resolves modes to booleans before runtime or inspection. Both operator assembly and direct `AppConfig` construction reject unsafe identity configurations. Production requires REST JWT verification with issuer, audience and JWKS, MCP OIDC and a supported provider. Development or simulation requires an explicit `test:` namespace. A development REST authentication environment uses semantic JWT verification even with mode `jwt` and an OIDC recipe; it is rejected in production and requires test isolation locally. Identity settings are registered in non-secret inspection. Automatic OAuth authorization requires effective selection, durable SQLite storage and a nonblank connector configuration encryption secret derived from `UMBOD_ROOT_SECRET`. Explicit OAuth `true` still requires all prerequisites and fails validation otherwise, including when selection is explicitly disabled. Storage durability uses the same predicate during policy resolution and runtime validation: blank paths, `:memory:` paths and paths containing `mode=memory` are not durable. In-memory and SQLite memory paths are rejected for exposed authorization. Runtime execution remains disabled. See the [environment reference](../../../../docs/operations/configuration.md#personal-connections-identity-policy).

### `inspection.py`

**Read when working with:** Configuration inspection and display behavior.

`RestConfig.metrics_enabled` and `McpConfig.metrics_enabled` default to true. Embedded hosts may disable the dedicated metrics listeners while retaining application instrumentation; normal service configurations remain enabled.
