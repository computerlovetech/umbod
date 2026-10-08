# Admin Infrastructure

**Module responsibility:** Browser HTTP transport, validated public configuration, and administration API composition.

## Modules

- `transport.ts`: Transport port, Zod boundary validation, cancellation, same-origin credentials, web-request marker, authentication rejection without automatic navigation or replay, an explicit `navigateToSignIn` user-action helper, and optional externally supplied bearer credentials.
- `public-configuration.ts`: Configuration provider port and browser/in-memory adapters. Deployment configuration uses public `apiBaseUrl` and `mcpBaseUrl` keys from `/app-config.json`. Development defaults are `/api` and `http://localhost:8011` when that resource is absent.
- `admin-api.ts`: Composite `AdminApi` over an injected `Transport`, bounded route adapters, and account identity.
- `browser-request.ts`: Presentation error mapping for detail clients and component loaders.
- `schema.ts`: Shared schema helpers.

Feature schemas remain in the parent administration module. Adapter paths start at `/admin/`; the transport prepends the configured API base.
