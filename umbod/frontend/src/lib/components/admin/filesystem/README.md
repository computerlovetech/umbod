# Filesystem access editor

- `FilesystemAccessPage.svelte`: Browser API composition, initial mount loading and disposal.
- `FilesystemAccessEditor.svelte`: Compact root policy editor with group cards, permission chips, a sticky save bar, contextual creation guidance, collapsed access details/read-only recursive grants and explicit confirmation dialogs. Legacy direct rows remain repairable/removable; blank recursive identities and empty permissions are labelled read-only.
- `FilesystemConfirmationDialog.svelte` and `confirmation-dialog.ts`: Scoped native modal dialogs opened by a DOM attachment, initial Cancel focus, native background inertness and focus containment. Escape and Cancel preserve drafts; native close runs before dismissal for opener focus restoration. No reactive synchronization effect or shared modal change.
- `confirmation-dialog.test.ts`: Native dialog lifecycle and draft-preserving Escape behavior; browser-native focus containment/restoration remain browser verification responsibilities.
- `filesystem-access-state.svelte.ts`: Draft ownership, canonical dirty comparison, staged removal, empty-policy confirmation, revision-checked saving and explicit discard/reload. Failed writes preserve drafts and block further saves until authoritative reload.
- `filesystem-access-state.test.ts`: State behavior through the administration port.
- `filesystem-components.test.ts`: Accessible controls and administration navigation.
