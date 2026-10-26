# Components

**Module responsibility:** Reusable Svelte presentation, interaction, and component-scoped state.

**Read when working with:** Shared UI behavior, visual components, accessibility-visible controls, or reusable interaction patterns.

## Composition boundaries

Shared components own reusable layout, presentation mechanics, and general accessibility behavior. Actor-specific parents own data adaptation, eligibility, actions, wording, and presentation choices. When a section needs to vary between administration and ordinary-user views, make it replaceable through typed Svelte snippets rather than coupling whole actor views or adding role flags.

Actors may deliberately choose the same shared presenter. A later actor-specific requirement should normally be implemented by changing that actor's supplied section, without modifying the shared layout or the other actor's composition. Keep shared presentation types and formatting independent of actor models, controllers, and clients. Use CSS custom properties for supported styling variation rather than reaching into another component's markup.

Do not create extension points for hypothetical differences or wrap every element. Small amounts of actor-owned composition markup are preferable to duplicated rendering, validation, business rules, and keyboard behavior. Changes to genuinely shared mechanics or design tokens may affect all consumers and must be verified for those consumers.

See [ADR-007: Actor-Specific Composition of Shared UI Components](../../../../project/architecture-records/ADR-007-actor-specific-ui-composition.md).

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

**Read when working with:** Administration shell, connectors, permissions, OpenAPI, or downstream MCP interfaces. Mutation forms dispatch typed browser operations through `$lib/admin/operations/browser-submit`; callbacks preserve reconciliation and register pending-state cleanup. Administration `connectors/ToolCard.svelte` owns its tool data and control composition over the neutral shared tool card. Dashboard owns a separate `CatalogueToolCard.svelte` composition rather than importing the admin card. Shared `tools/` presenters provide description, parameter and output-schema rendering; actor compositions may select or replace them independently.

### `admin/personal-mcp-servers/`

`PersonalServerRegistration.svelte` and the connector-keyed `PersonalServerPolicyPanel.svelte` compose `PolicyFields.svelte`, `PolicyForm` and scoped `PersonalServerFormState` without an inventory or selection owner. Registration suggests the tool prefix and path suffix from the server name using shared `admin/shared/connector-name-suggestions.ts` normalization; manual edits, including clearing either field, preserve independent overrides until the next registration. `AdminConfigurationField.svelte` supports non-editable input prefixes and length limits. The registration path displays `/mcp/proxies/` separately from its editable suffix without presenting it as a connection URL. Metadata, endpoint and OAuth fields provide placeholders and accessible purpose guidance; provider URLs, permissions and credentials are never inferred. OAuth application setup and token authentication use the shared `admin/shared/Select.svelte` control, whose overlays stay within native dialogs and are removed on unmount. Registration availability is checked through the read-only instance-configuration port and fails closed independently of Shared setup. Confidential secrets remain transient; policy conflicts and unknown writes require explicit authoritative reload without replay. Registration paths identify definitions, not shared proxy connections. Personal details explain whole-server group trust and point users to Dashboard for authorization and private discovery.

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

`ConnectionCard.svelte` presents clear local health, one contextual recovery action, optional connection details and confirmed disconnect. `ConnectionStatusBadge.svelte` shares status between details and the connector list; `ConnectionActions.svelte` reuses the connector three-dot menu for secondary owner-scoped actions. Embedded presentation lives inside the dashboard's selected connector detail. Explicit sign-in opens the provider automatically, retaining a manual fallback without restarting the attempt. Local health and renewal capability remain separate from tool eligibility; recovery never resumes an earlier operation automatically. Reactive behavior and user API ports live in `$lib/personal-connections/`, not administration state. See `personal-connections/README.md`.

### `feedback/`

**Read when working with:** Toasts and user feedback state or presentation.

### `header/`

**Read when working with:** Header layout and account presentation.

### `dashboard/`

`Dashboard.svelte` composes the single user dashboard with the shared workspace shell, permission-filtered connector catalogue, embedded personal MCP actions and compact client setup. `ConnectorWorkspace.svelte` reuses the connector sidebar and split workspace for one combined shared/personal list. `ConnectorDetail.svelte` reuses summary primitives without publication controls and explains administrator-managed definitions; `CatalogueCapabilities.svelte` provides read-only capability groups and search. Administrator navigation appears only when the independent current-user read resolves allowed access; catalogue state remains independent. State and validated clients live in `$lib/dashboard/`.

### `shared/`

**Read when working with:** Cross-cutting controls and display components reused across features. `workspace/` supplies the neutral navigation/account shell and logout state; `mcp-setup/` supplies the endpoint-driven full and compact client instructions used by administration and the dashboard. `tools/` supplies the neutral snippet-based tool card, optional presenters and schema display types. See `shared/README.md`.
