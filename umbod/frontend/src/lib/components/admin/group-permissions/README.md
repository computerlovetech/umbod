# Group permissions

Administration permissions are organized into Connectors and Filesystem subpages under one workspace navigation entry.

- `GroupPermissionsTabs.svelte`: Accessible resource navigation shared by both permission subpages; the active route determines the current link.
- `GroupPermissionsManager.svelte`: Connectors permissions page, group registration/removal, selected group overview, capability grants and explicit saves.
- `group-permissions-state.svelte.ts`: Connector grant drafts, group selection, capability expansion, unavailable saved grant cleanup and save feedback.
- `group-permissions-loader.ts`: Selected group permission reads and loading state boundaries.
- `group-permissions-components.test.ts`: Accessible connector permission presentation and resource navigation.
- `group-permissions-state.test.ts` and `group-permissions-state.spec.ts`: Group selection, capability grant behavior and draft lifecycle.
- `../filesystem/README.md`: Filesystem permission overview, isolated modal drafts and revision-checked policy saves.
