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
`AdminSplitWorkspace` to stack its sidebar when the content area is narrow. Its accessible Log out button uses the injected logout navigation port independently of account identity; navigation occurs only on explicit user action. Both account presentations hide only the email row when the identity email is null, retaining the name and picture. Nullable API responses require a coordinated frontend build and release because older clients require string emails.

## Submodules

### `admin/`

**Read when working with:** Administration shell, connectors, permissions, OpenAPI, or downstream MCP interfaces. Mutation forms dispatch typed browser operations through `$lib/admin/operations/browser-submit`; callbacks preserve reconciliation and register pending-state cleanup.

### `admin/personal-mcp-servers/`

`PersonalServersPage.svelte` owns the mounted allowlist lifecycle and scoped administration state. It injects the separate instance-configuration port for a fail-closed registration preflight, with resolved registration and user OAuth availability shown independently. Explicit reload refreshes settings alongside inventory; startup settings remain read-only. `PolicyFields.svelte` and `PolicyForm` keep fresh confidential secrets transient. Explicit confirmations separate policy invalidation, publication, withdrawal and deletion; conflicts and unknown writes require manual reload without replay. Server registration paths are identifiers, not shared personal proxy connections. Shared MCP workspaces exclude personal definitions before loading capability bundles.

### `admin/group-permissions/`

`GroupPermissionsManager.svelte` presents assignable targets and saved grants for unavailable connectors, including capability-only grants. Removal stages explicit disabled changes for the existing Save permissions action; it does not republish connectors or automatically revoke grants. The personal MCP server selected metadata exposes Server ID for matching these grants.

### `admin/mcp-setup/`

`McpSetupGuide.svelte` provides connection instructions and a copyable prompt referring to the shared `umbod://setup/agent-instructions` MCP resource for user-scoped agent discovery setup.

### `admin/overview/`

**Read when working with:** Overview cards, connector breakdown, partial-data warnings or connector attention presentation. See `admin/overview/README.md`.

### `admin/instance-configuration/`

**Read when working with:** Read-only Instance settings, friendly value presentation, technical details or raw-value copying. See `admin/instance-configuration/README.md`.

### `personal-connections/`

`PersonalConnections.svelte` owns the mounted page lifecycle; `ConnectionCard.svelte` presents explicit enablement, owner authorization health, manual status checks and renewal, manual attempt inspection, discovery and confirmed disconnect. Local health and renewal capability remain separate from tool eligibility; recovery never resumes an earlier operation automatically. Reactive behavior and user API ports live in `$lib/personal-connections/`, not administration state.

### `feedback/`

**Read when working with:** Toasts and user feedback state or presentation.

### `header/`

**Read when working with:** Header layout and account presentation.

### `home/`

**Read when working with:** Landing-page presentation.

### `shared/`

**Read when working with:** Cross-cutting controls and display components reused across features.
