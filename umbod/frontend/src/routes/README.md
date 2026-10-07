# Routes

**Module responsibility:** SvelteKit routing boundary containing layouts, pages, server loaders, and HTTP endpoints.

**Read when working with:** Navigation, page composition, route data loading, form actions, or frontend server endpoints.

## Submodules

### `admin/`

**Read when working with:** Administration pages, route-local loaders, actions, or API endpoints.

### `admin/+page.server.ts` and `admin/+page.ts`

**Read when working with:** Server-loaded overview counts and forwarding the server payload while retaining argument-free navigation-loader compatibility. Presentation lives in `$lib/components/admin/overview/`; aggregation lives in `$lib/admin/overview/`.

### `system/`

**Read when working with:** Frontend health and system endpoint behavior.
