# User dashboard UI specification

Status: Implemented and verified.

## Purpose

Provide one user dashboard for discovering available connectors and tools, using Umbod from an MCP client, and managing administrator-approved personal MCP access. Shared and personal MCP servers belong to the same experience. Connection ownership changes permitted actions, not the user-facing domain vocabulary.

## Routes and navigation

- Introduce `/dashboard` outside the administrator route layout.
- Remove `/settings/connections`; do not install a redirect or compatibility route.
- Replace navigation links to Connections with Dashboard, linking to `/dashboard`.
- Use Dashboard for the page heading and document title.
- Keep `/admin` as the administrator workspace, with its existing authorization boundary.
- The dashboard is one page without management tabs. Do not add dashboard subpages for connector registration, publication, group permissions, or server policy.
- Ordinary users must not see administrator navigation or management controls. Their absence must not depend on failed administrator API requests.
- The dashboard remains usable when personal MCP support is disabled.

## Page structure

### Common shell

Reuse the administrator workspace's visual language, spacing, surfaces, typography, responsive behavior, and account presentation through neutral shared components. Do not render a second global header above the dashboard shell.

The dashboard heading has no explanatory subtitle, welcome paragraph, or onboarding banner. Omit summary cards in the initial version. Do not copy administration-wide statistics, draft counts, permission-group counts, publication state, or configuration warnings into the user dashboard.

### Connector catalogue

Render the connectors available to the authenticated user in one catalogue. Native, OpenAPI, and MCP connectors retain their actual kinds; native and OpenAPI connectors must not be called MCP servers.

Each entry presents:

- Display name.
- Kind: Native, OpenAPI, or MCP server.
- Its concise administrator-provided capability description, when present.
- User-visible availability, when known.
- For MCP servers, Shared or Personal ownership where relevant.
- An action to inspect available tools and other supported capabilities.

Shared and personal MCP entries use the same summary and details structure. Do not introduce a separate Connections list or a parallel personal-server dashboard.

Only published, permitted connector information may appear. Capability lists and any counts are restricted to what the current user may access. Administrator-provided catalogue descriptions are content, not introductory UI explanations, and should be retained.

Shared connector entries are read-only. Do not show disabled administration controls as placeholders. Do not display downstream server endpoints, credentials, client policy, publication controls, group grants, configuration revisions, or instance-wide discovery diagnostics.

### Connector details

Use Show details to expand an entry inline and Hide details to collapse it. The expanded content shows connector identity and permitted capabilities without routing users into an administrator page. Capability information is read-only; viewing a tool must not invoke it.

MCP server details reuse common summary and status presentation across ownership modes. Personal actions appear first in a distinct personal-access section, before potentially long capability inventories. Capability descriptions expand individually; names and kinds remain visible without the descriptive text. Administrator configuration remains a separate composition, not hidden editable fields in the user view.

### Personal MCP actions

Personal MCP entries expose only actions already supported by owner-scoped APIs and permitted by administrator policy. Users do not register servers or edit server endpoints, shared credentials, OAuth client policy, approved tools, or group permissions.

Preserve the distinction between personal enablement, saved authorization, and runtime availability. A successful sign-in must not alone imply that tools are available.

Use the existing lifecycle guards to select applicable actions; do not render every action for every state:

- Enable or Disable for personal enablement.
- Sign in or Sign in again for authorization.
- Check authorization status and Renew authorization where supported.
- Discover tools where permitted by the current authorization and policy.
- Disconnect to remove the user's saved authorization, preserving existing confirmation behavior.
- Continue sign-in, Check sign-in status, and Cancel sign-in for a known pending authorization attempt.

These operations affect only the current user's personal state. They must not modify shared server configuration or another user's state. Do not treat Disconnect as a synonym for disabling the personal server.

Keep pending authorization state stable while inspecting other dashboard content. Prevent duplicate submissions during an operation. Show outcomes beside the relevant server rather than replacing the whole dashboard.

### MCP client setup

Provide one compact inline MCP setup section within the dashboard, with the Umbod endpoint and copy control visible and client-specific instructions expandable. Reuse the endpoint-driven MCP setup component currently used by administration.

This is client setup for using Umbod, not provisioning or configuring downstream connectors. Keep the Umbod endpoint, copy controls, and necessary client-specific steps. Remove introductory marketing text and repeated explanations. Do not expose administrator-only configuration through this component.

## Content rules

- Do not use Connections as a page, navigation, section, or entity label.
- Use Dashboard, Connectors, MCP server, Shared, Personal, and Tools consistently.
- Prefer short action labels and factual statuses to explanatory paragraphs.
- Remove routine hints, policy essays, summary-card explanations, and duplicated ownership explanations.
- Retain errors, required consent information, external-window indicators, accessible labels, and necessary confirmations.
- Do not translate unknown or unavailable data into zero, disabled, or healthy states.

## Loading, authentication, and failure behavior

- Initial loading uses a stable shell and bounded loading placeholders rather than administrator data or misleading zero counts.
- Load catalogue and MCP setup independently where possible. A personal-action failure must not hide shared connectors or setup information.
- An empty permitted catalogue shows No connectors available. Do not offer administrator setup actions.
- An empty capability list shows No tools available where the detail is specifically a tools view.
- An expired or missing session produces a concise Sign in required state using the application's supported authentication flow. Clear prior-user catalogue and personal data.
- A catalogue request failure shows Couldn't load connectors with Retry. Keep unrelated usable sections available.
- Permission withdrawal removes protected information on refresh and invalidates stale actions. The server remains the authority for every operation.
- Personal feature unavailability suppresses personal controls without disabling the dashboard.
- Operation errors are local, concise, and redacted. Preserve valid state and permit a deliberate retry after the outcome is known.
- Navigation or disposal cancels subscriptions and prevents stale responses from changing a later page or another user's state.

## Accessibility and responsive behavior

- Use one page-level heading, named sections, and semantic lists for catalogue entries.
- All details and personal actions are keyboard accessible with visible focus.
- Announce operation outcomes without moving focus unnecessarily. Loading controls expose their pending state.
- Details presented in a dialog must have an accessible name, correct focus containment, Escape handling, and focus restoration.
- Status and ownership must not rely on color alone.
- Collapse the catalogue to one column on narrow screens. Wrap long names and endpoint text without horizontal page overflow.
- Preserve server identity and action labels on narrow screens; do not hide actions behind hover.

## Component and data boundaries

- Extract neutral shell and presentation primitives from administration; retain `AdminShell` as its administration-specific composition.
- Share connector and MCP server presentation where information has the same meaning. Keep administrator configuration and personal actions as separate supplied sections.
- Reuse owner-scoped personal MCP state, authorization lifecycle, transport, and validation rather than rewriting them for the dashboard.
- Reuse the MCP setup component and endpoint resolution rather than duplicating client instructions.
- Do not reuse the administrative overview loader for ordinary users.
- Introduce an authenticated user catalogue projection that applies publication and effective capability permissions before returning data. Do not expose administrative inventory and filter it in the browser.
- Resolve permissions consistently with MCP runtime access. Personal capability observations remain principal-scoped and constrained by administrator approval.
- Mount general user dashboard read access independently of the personal MCP feature flag.
- Keep `/api/admin` protected. Sharing UI must not broaden its authorization rules.
- Internal personal-connections module and API names need not change merely to remove Connections from visible UI.

## Acceptance scenarios

### Ordinary user dashboard

Given an authenticated non-administrator with access to published connectors, when they open `/dashboard`, then they see their permitted catalogue and MCP setup without administrator tabs, configuration controls, or administrator API requests.

### Consistent MCP presentation

Given access to shared and personal MCP servers, when the catalogue renders, then both use the same entry and detail structure, and ownership changes only relevant labels, statuses, and permitted personal actions.

### Read-only shared access

Given a shared connector, when its details are opened, then permitted capabilities are visible and no global enablement, credential, publication, discovery-management, or permission-editing action is available.

### Personal state isolation

Given an approved personal MCP server, when the user performs a permitted personal action, then only that user's state changes and neither the shared definition nor another user's authorization is modified.

### Authorization is not availability

Given a personal server with saved authorization but no available approved tools, when its status renders, then sign-in and tool availability remain distinguishable and the UI does not report readiness based only on authorization.

### Personal support disabled

Given a deployment without personal MCP support, when an authenticated user opens `/dashboard`, then the permitted shared catalogue and MCP setup still load and personal actions are absent.

### Permission filtering

Given draft, unpublished, or inaccessible connector and capability records, when catalogue or details are requested, then those records and their administrative information are not returned or displayed.

### Access changes

Given an open dashboard whose user loses access to a connector, when data refreshes or an action is attempted, then protected information is removed or the action is rejected without restoring stale access.

### Partial failure

Given a loaded shared catalogue, when a personal operation fails, then its error appears beside that server and the catalogue and MCP setup remain usable.

### Session change

Given loaded personal information, when authentication expires or the active identity changes, then prior-user information is cleared and stale responses cannot repopulate it.

### Route removal

Given a request to `/settings/connections`, when routing resolves, then the removed route does not render or redirect; application navigation uses `/dashboard` exclusively.

### Minimal copy

Given any normal dashboard state, when the page renders, then no introductory explanation, ownership essay, or administrator-management guidance is shown; names, catalogue descriptions, concise statuses, actionable errors, and necessary confirmations remain.

## Implementation decisions

- One catalogue with inline expandable details, followed by compact MCP setup with expandable client instructions.
- Initial account presentation uses the existing hidden-identity fallback with explicit logout; no administrator switch or administrator identity probe is introduced. An opaque catalogue identity key clears prior-user personal state when the authenticated account changes.
- Personal actions retain their existing lifecycle guards and confirmation behavior. Returning to the loaded dashboard revalidates identity and permissions without polling, navigation, or operation replay.

## Verification for implementation

Run frontend tests and type/Svelte checks. Verify ordinary-user, administrator, empty, partial-failure, and personal-feature-disabled states in the Docker Compose-served browser. Verify authorization and user-catalogue application changes with the repository's Kind runtime integration suite. Update affected module README indexes when introducing shared components, routes, or API boundaries.
