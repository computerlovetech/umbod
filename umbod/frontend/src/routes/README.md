# Routes

**Module responsibility:** Static SvelteKit SPA layouts, universal browser loaders, navigation, and page composition. Root SSR is disabled; adapter-static emits the `200.html` fallback.

## Entry points

- `+layout.ts` loads validated public configuration from `/app-config.json` before application requests.
- `admin/+layout.ts` resolves account identity through the authenticated backend `/admin/users` adapter and maps rejected authentication and forbidden access to safe 401/403 errors.
- `+error.svelte` catches route and admin layout load failures, presents safe access-denied or generic error text, and offers explicit sign-in only for 401 plus user-triggered logout for both 401 and 403. Logout remains available without account identity or a working configuration fetch, with a fixed gateway-only recovery destination.
- `settings/connections/+page.svelte` composes the owner-scoped personal connections UI, including local authorization status and explicit renewal recovery, without the admin layout or account authorization endpoint.
- `admin/+page.ts` composes the administration overview through browser API adapters.
- `admin/personal-mcp-servers/+page.ts` reads only the selected URL identifier; its thin page composes the component-scoped personal allowlist administration UI. Initial API reads are limited to inventory, selected definition and OAuth policy. Admin navigation and the shared MCP proxy workspace link to this separate administration boundary.
- Administration `+page.ts` modules load lists, selected details, permissions, instance settings, and MCP setup data.
- Connector detail routes redirect to the corresponding workspace selection.

Mutation handlers live in `$lib/admin/operations/`; routes contain no server actions or aggregation endpoints. Rejected authentication remains an error without automatic navigation or request replay. The 401 error page offers a user-initiated full navigation to `/oauth2/sign_in` with the return location; forbidden access offers no sign-in action.
