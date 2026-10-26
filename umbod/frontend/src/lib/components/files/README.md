# Files components

**Module responsibility:** Compact normal-user Files presentation outside the admin layout.

- `FilesPage.svelte` composes WorkspaceShell, starts independent administration presentation lookup on mount, and loads Files from SvelteKit afterNavigate for initial navigation and browser history. Disposal invalidates reads and pending creation presentation.
- `FilesContent.svelte` presents Files, visited-folder links, loading/denied/failure/empty states, accessible file/folder items and selected file metadata. Parent navigation is explicit and never triggers automatic ancestor reads.
- `NewFolderForm.svelte` presents one inline name field with initial focus, Escape cancellation, disabled pending input and submit, preserved denied/conflicting drafts, and explicit reload for uncertain writes.
- `files-components.test.ts` verifies navigation, URL/history callbacks, states, safe metadata and supported controls.

State and validated I/O live in `$lib/files/`. No content actions or administration-based permission guesses are exposed.
