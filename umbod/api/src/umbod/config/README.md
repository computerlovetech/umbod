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

### `secret_derivation.py`

**Read when working with:** Secret generation and resolution.

### `app.py`

**Read when working with:** Internal application configuration consumed at runtime.

### `validate.py`

**Read when working with:** Cross-field configuration constraints and startup validation.

### `inspection.py`

**Read when working with:** Configuration inspection and display behavior.
