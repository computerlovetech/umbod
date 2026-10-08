# Routes

**Module responsibility:** Static SvelteKit SPA layouts, universal browser loaders, navigation, and page composition. Root SSR is disabled; adapter-static emits the `200.html` fallback.

## Entry points

- `+layout.ts` loads validated public configuration from `/app-config.json` before application requests.
- `admin/+layout.ts` resolves account identity through the authenticated backend `/admin/users` adapter.
- `admin/+page.ts` composes the administration overview through browser API adapters.
- Administration `+page.ts` modules load lists, selected details, permissions, instance settings, and MCP setup data.
- Connector detail routes redirect to the corresponding workspace selection.

Mutation handlers live in `$lib/admin/operations/`; routes contain no server actions or aggregation endpoints. Authentication expiry uses full navigation to `/oauth2/sign_in` with the return location; forbidden access remains an error.
