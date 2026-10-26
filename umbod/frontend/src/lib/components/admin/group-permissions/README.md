# Group permissions

Administration permissions are organized into Connectors and Filesystem subpages under one workspace navigation entry.

- `GroupPermissionsTabs.svelte`: Accessible resource navigation shared by both permission subpages; the active route determines the current link.
- `GroupPermissionsManager.svelte`: Connectors permissions page, shared catalogue registration/deletion, selected group overview, capability grants and explicit saves. Deletion is blocked by connector, capability or filesystem references; registration grants no access and creates no IdP membership.
- `group-permissions-state.svelte.ts`: Connector grant drafts, group selection, capability expansion, unavailable saved grant cleanup and save feedback.
- `group-permissions-loader.ts`: Selected group permission reads and loading state boundaries.
- `group-permissions-components.test.ts`: Accessible connector permission presentation and resource navigation.
- `group-permissions-state.test.ts` and `group-permissions-state.spec.ts`: Group selection, capability grant behavior and draft lifecycle.
- `shared/GroupRegistrationDialog.svelte` and `shared/group-registration-state.svelte.ts`: Exact group-claim registration modal with independent immediate persistence, no issuer or permissions, and cancellable pre-submit state. Used by the filesystem workspace.
- `shared/native-dialog.ts`: Native modal attachment with focus handling, cleanup and optional pending-operation cancellation guard; filesystem dialogs retain a compatibility export.
- `../filesystem/README.md`: Filesystem permission overview, isolated modal drafts and revision-checked policy saves.
