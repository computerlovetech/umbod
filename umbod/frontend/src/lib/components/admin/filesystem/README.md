# Filesystem access editor

- `FilesystemAccessPage.svelte`: Browser API composition, initial mount loading and disposal.
- `FilesystemAccessEditor.svelte`: Filesystem subpage under Group permissions, with shared resource tabs and a split overview with group selection, identity and permission summaries, a top-right add action, staged removal, a sticky save bar and collapsed access details/read-only recursive grants. Legacy direct rows remain repairable/removable; blank identities and empty permissions are labelled.
- `FilesystemGroupDialog.svelte` and `filesystem-group-editor-state.svelte.ts`: Isolated add/edit drafts, strict identity/permission and duplicate validation, selection and explicit application to the policy draft. Cancel and Escape leave the policy unchanged; native dialog attachment provides focus containment and restoration.
- `filesystem-group-editor-state.test.ts`: Modal draft cancellation/application, validation and selection behavior through the administration port.
- `FilesystemConfirmationDialog.svelte` and `confirmation-dialog.ts`: Scoped native modal dialogs opened by a DOM attachment, initial Cancel focus, native background inertness and focus containment. Escape and Cancel preserve drafts; native close runs before dismissal for opener focus restoration. No reactive synchronization effect or shared modal change.
- `confirmation-dialog.test.ts`: Native dialog lifecycle and draft-preserving Escape behavior; browser-native focus containment/restoration remain browser verification responsibilities.
- `filesystem-access-state.svelte.ts`: Draft ownership, atomic group application, canonical dirty comparison, staged removal, empty-policy confirmation, revision-checked saving and explicit discard/reload. Failed writes preserve drafts and block further saves until authoritative reload.
- `filesystem-access-state.test.ts`: State behavior through the administration port.
- `filesystem-components.test.ts`: Accessible controls and administration navigation.
