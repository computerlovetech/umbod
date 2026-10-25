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
existing logo. Shared `WorkspaceShell`, composed by `AdminShell` and the user dashboard, provides the inline-size container used by
`AdminSplitWorkspace` to stack its sidebar when the content area is narrow. Its accessible Log out button uses the injected logout navigation port independently of account identity; navigation occurs only on explicit user action. Both account presentations hide only the email row when the identity email is null, retaining the name and picture. Nullable API responses require a coordinated frontend build and release because older clients require string emails.

## Submodules

### `admin/`

**Read when working with:** Administration shell, connectors, permissions, OpenAPI, or downstream MCP interfaces. Mutation forms dispatch typed browser operations through `$lib/admin/operations/browser-submit`; callbacks preserve reconciliation and register pending-state cleanup.

### `admin/personal-mcp-servers/`

`PersonalServerRegistration.svelte` and the connector-keyed `PersonalServerPolicyPanel.svelte` compose `PolicyFields.svelte`, `PolicyForm` and scoped `PersonalServerFormState` without an inventory or selection owner. Registration availability is checked through the read-only instance-configuration port and fails closed independently of Shared setup. Confidential secrets remain transient; policy conflicts and unknown writes require explicit authoritative reload without replay. Registration paths identify definitions, not shared proxy connections. Personal details explain whole-server group trust and point users to Dashboard for authorization and private discovery.

### `admin/downstream-mcp-connectors/`

`DownstreamMcpPageContent.svelte` owns the single Shared/Personal workspace selection. Add opens Shared setup directly unless personal registration is enabled, in which case it offers both modes. Mode-discriminated detail bundles load shared catalogues only for Shared definitions; personal OAuth forms are mounted and disposed separately. `DownstreamMcpWorkspace.svelte` reuses the common sidebar, detail metadata and publication/deletion action menu while hiding shared setup, readiness, discovery and capability controls for Personal definitions. `DownstreamMcpMutationState` guards personal common mutations, explicit grant-cleanup conflicts, authentication loss and unknown outcomes without mutation replay or stale-list reconciliation. Independent registration and policy lock sources gate all workspace changes; uncertain registration remains locked after dialog close until explicit full workspace reload.

### `admin/group-permissions/`

`GroupPermissionsManager.svelte` presents assignable targets and saved grants for unavailable connectors, including capability-only grants. Removal stages explicit disabled changes for the existing Save permissions action; it does not republish connectors or automatically revoke grants. The personal MCP server selected metadata exposes Server ID for matching these grants.

### `admin/mcp-setup/`

`McpSetupGuide.svelte` provides connection instructions and a copyable prompt referring to the shared `umbod://setup/agent-instructions` MCP resource for user-scoped agent discovery setup.

### `admin/overview/`

**Read when working with:** Overview cards, connector breakdown, partial-data warnings or connector attention presentation. See `admin/overview/README.md`.

### `admin/instance-configuration/`

**Read when working with:** Read-only Instance settings, friendly value presentation, technical details or raw-value copying. See `admin/instance-configuration/README.md`.

### `personal-connections/`

`ConnectionCard.svelte` presents explicit personal enablement, owner authorization health, manual status checks and renewal, manual attempt inspection, discovery and confirmed disconnect. Embedded presentation lives inside the dashboard's common connector card. Local health and renewal capability remain separate from tool eligibility; recovery never resumes an earlier operation automatically. Reactive behavior and user API ports live in `$lib/personal-connections/`, not administration state.

### `feedback/`

**Read when working with:** Toasts and user feedback state or presentation.

### `header/`

**Read when working with:** Header layout and account presentation.

### `dashboard/`

`Dashboard.svelte` composes the single user dashboard with the shared workspace shell, permission-filtered connector catalogue, embedded personal MCP actions and compact client setup. `ConnectorCard.svelte` supplies the common shared/personal summaries and inline read-only capability details. It shows shared administrator navigation only when its independent current-user read resolves allowed administration access; catalogue state remains independent. State and validated clients live in `$lib/dashboard/`.

### `shared/`

**Read when working with:** Cross-cutting controls and display components reused across features. `workspace/` supplies the neutral navigation/account shell and logout state; `mcp-setup/` supplies the endpoint-driven full and compact client instructions used by administration and the dashboard.
