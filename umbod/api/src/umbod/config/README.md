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

**Read when working with:** Internal application configuration consumed at runtime, including the independently enabled OTLP receiver and its request limit. Operator OTLP bearer credentials are excluded from configuration inspection and redacted display.

### `validate.py`

**Read when working with:** Cross-field configuration constraints and startup validation.

### `inspection.py`

**Read when working with:** Configuration inspection and display behavior.
