# Routes

**Module responsibility:** Static SvelteKit SPA layouts, universal browser loaders, navigation, and page composition. Root SSR is disabled; adapter-static emits the `200.html` fallback.

## Entry points

- `+page.ts` redirects the root with 307 to `/dashboard`.
- `+layout.ts` loads validated public configuration from `/app-config.json` before application requests.
- `admin/+layout.ts` resolves account identity through the authenticated backend `/admin/users` adapter and maps rejected authentication and forbidden access to safe 401/403 errors.
- `+error.svelte` catches route and admin layout load failures, presents safe access-denied or generic error text, and offers explicit sign-in only for 401 plus user-triggered logout for both 401 and 403. Logout remains available without account identity or a working configuration fetch, with a fixed gateway-only recovery destination.
- `dashboard/+page.svelte` composes the authenticated user catalogue, owner-scoped personal MCP actions, and shared compact MCP client setup outside the admin layout. Its loader reads only public endpoint configuration. The dashboard independently starts fail-closed administration presentation and catalogue reads on mount; pending or failed admin lookup cannot delay the catalogue; `/settings/connections` has been removed without a redirect.
- `files/+page.svelte` composes normal-user Files outside the admin layout. URL node selection and browser history drive independent filesystem reads; folder creation is server-authoritative. See `$lib/files/README.md` and `$lib/components/files/README.md`.
- `admin/+page.ts` composes the administration overview through browser API adapters.
- `admin/downstream-mcp-connectors/+page.ts` loads one Shared/Personal inventory and selection. Personal details branch before shared catalogue and activation reads; component-scoped OAuth forms remain outside cached detail bundles.
- `admin/personal-mcp-servers/+page.ts` redirects with 307 to the unified MCP workspace, preserving valid selection and query parameters. No separate personal page or navigation remains.
- `admin/group-permissions/connectors/+page.ts` loads connector group permissions and validates connector/operation deep links; its page composes the wide Connectors permissions workspace.
- `admin/group-permissions/filesystem/+page.svelte` composes the wide Filesystem group overview and modal editor under Group permissions; component mount owns validated loading, explicit saves and authoritative reloads.
- `admin/group-permissions/+page.ts` and `admin/filesystem/+page.ts` redirect legacy URLs to the Connectors and Filesystem permissions subpages respectively, preserving query parameters and fragments.
- Administration `+page.ts` modules load lists, selected details, permissions, instance settings, and MCP setup data.
- Connector detail routes redirect to the corresponding workspace selection.

Mutation handlers live in `$lib/admin/operations/`; routes contain no server actions or aggregation endpoints. Rejected authentication remains an error without automatic navigation or request replay. The 401 error page offers a user-initiated full navigation to `/oauth2/sign_in` with the return location; forbidden access offers no sign-in action.
