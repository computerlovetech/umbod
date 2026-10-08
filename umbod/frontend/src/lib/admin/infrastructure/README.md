# Admin Infrastructure

**Module responsibility:** Browser HTTP transport, validated public configuration, and administration API composition.

## Modules

- `transport.ts`: Transport port, Zod boundary validation, cancellation, same-origin credentials, web-request marker, authentication rejection without automatic navigation or replay, an explicit `navigateToSignIn` user-action helper, and optional externally supplied bearer credentials.
- `public-configuration.ts`: Configuration provider port and browser/in-memory adapters. Deployment configuration uses public `apiBaseUrl` and `mcpBaseUrl` keys from `/app-config.json`. Optional `logout` is null or validated public `auth0Domain`, `clientId`, and fixed HTTPS `returnTo` values. Development defaults are `/api` and `http://localhost:8011` with gateway-only logout when that resource is absent.
- `logout.ts`: Logout navigation port, validated nested Auth0 URL builder, and injected full-browser navigation. User actions pass through gateway sign-out first; missing or unavailable configuration uses only the fixed `/signed-out.html` gateway return. No automatic navigation, cookie manipulation, or arbitrary query destination is supported.
- `admin-api.ts`: Composite `AdminApi` over an injected `Transport`, bounded route adapters, and account identity.
- `browser-request.ts`: Presentation error mapping for detail clients and component loaders.
- `schema.ts`: Shared schema helpers.

Feature schemas remain in the parent administration module. Adapter paths start at `/admin/`; the transport prepends the configured API base.
