# Components

**Module responsibility:** Reusable Svelte presentation, interaction, and component-scoped state.

**Read when working with:** Shared UI behavior, visual components, accessibility-visible controls, or reusable interaction patterns.

## Admin visual styling

`../styles/admin.css` defines semantic theme variables adapted from the website and
documentation palette. The admin shell, connector catalog and OpenAPI workspace,
and their shared controls consume these variables in component-scoped styles.
Keep presentation changes in those components; feature state and API adapters stay
in their existing modules. Use the semantic variables for surfaces, text, actions,
focus and feedback instead of duplicating literal colours. Other feature-specific
styles are being migrated incrementally.

The shell uses `static/umbod-logo.svg`, copied from the website's existing logo.

## Submodules

### `admin/`

**Read when working with:** Administration shell, connectors, permissions, OpenAPI, or downstream MCP interfaces.

### `feedback/`

**Read when working with:** Toasts and user feedback state or presentation.

### `header/`

**Read when working with:** Header layout and account presentation.

### `home/`

**Read when working with:** Landing-page presentation.

### `shared/`

**Read when working with:** Cross-cutting controls and display components reused across features.
