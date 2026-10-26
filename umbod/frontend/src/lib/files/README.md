# Files

**Module responsibility:** Normal-user filesystem browsing and folder creation, independent of administration.

- `api.ts` defines the filesystem port. `domain/schemas.ts` validates UUIDs, core NodeSummary metadata, root-parent empty objects, timestamps, revision, child lists and outbound folder bodies.
- `infrastructure/in-memory-api.ts` supplies the first port adapter for isolated tests. It is never automatically substituted for real user data.
- `infrastructure/filesystem-route.ts` uses the shared validated transport for only root GET, node GET, children GET and directory POST under `/me/filesystem`. `files-api.ts` wires the browser client.
- `state/files-state.svelte.ts` loads the URL-selected node, reads children only for directories, tracks visited folder links, and discards stale or disposed reads with generation checks and cancellation. Deep links never read ancestors.
- `state/new-folder-state.svelte.ts` owns the inline draft, pending locks, server-denied and collision feedback, parent-captured reconciliation and uncertain-write locks. Confirmed creation in the unchanged ready view appends directly; returning to the parent during a pending write triggers an authorized reload instead, invalidating any older in-flight listing before it can overwrite the confirmation. No write is replayed automatically. Unknown outcomes require explicit successful folder reload before another attempt, including after navigation away and back.
- `errors.ts` maps safe user-facing read and creation failures.
- `fixtures.test-support.ts` supplies plain test-only nodes for isolated port tests or HTTP mocks. Production imports no fixture.
- Port, schema, HTTP and state tests cover malformed payloads, denial, collision, explicit retry, navigation races and disposal.

Presentation lives in `$lib/components/files/`; `/files?node=UUID` is the URL source of truth. Breadcrumbs represent visited locations, not an authoritative ancestry or permission claim. The root label is Files. Access is enforced by each server operation, never inferred from administration or a successful browse. There are no upload, content, sharing, owned/shared listings, search or pagination calls.
