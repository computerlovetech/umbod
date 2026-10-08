# Components

**Module responsibility:** Reusable Svelte presentation, interaction, and component-scoped state.

**Read when working with:** Shared UI behavior, visual components, accessibility-visible controls, or reusable interaction patterns.

## Admin visual styling

`../styles/admin.css` defines semantic theme variables adapted from the website and
documentation palette. The admin shell, native/OpenAPI/MCP connector workspaces,
prompt and resource catalogs, group permissions, MCP setup, instance configuration,
configuration and confirmation dialogs, and shared controls and feedback consume
these variables in component-scoped styles. The home page, app header and global
light-theme defaults use the same palette.
Keep presentation changes in those components; feature state and API adapters stay
in their existing modules. Use the semantic variables for surfaces, text, actions,
focus and feedback instead of duplicating literal colours. Keep intentional vendor
logo colors in the MCP setup guide.

The shell and app header use `static/umbod-logo.svg`, copied from the website's
existing logo. `AdminShell` provides the inline-size container used by
`AdminSplitWorkspace` to stack its sidebar when the content area is narrow. Its accessible Log out button uses the injected logout navigation port independently of account identity; navigation occurs only on explicit user action.

## Submodules

### `admin/`

**Read when working with:** Administration shell, connectors, permissions, OpenAPI, or downstream MCP interfaces. Mutation forms dispatch typed browser operations through `$lib/admin/operations/browser-submit`; callbacks preserve reconciliation and register pending-state cleanup.

### `admin/overview/`

**Read when working with:** Overview cards, connector breakdown, partial-data warnings or connector attention presentation. See `admin/overview/README.md`.

### `admin/instance-configuration/`

**Read when working with:** Read-only Instance settings, friendly value presentation, technical details or raw-value copying. See `admin/instance-configuration/README.md`.

### `feedback/`

**Read when working with:** Toasts and user feedback state or presentation.

### `header/`

**Read when working with:** Header layout and account presentation.

### `home/`

**Read when working with:** Landing-page presentation.

### `shared/`

**Read when working with:** Cross-cutting controls and display components reused across features.
