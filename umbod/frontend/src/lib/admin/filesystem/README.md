# Filesystem administration

Root-only direct group access configuration through the `FilesystemAdministration` port.

- `port.ts`: Read and revision-checked replacement operations.
- `domain/schemas.ts`: Separate observed legacy response and strict submission Zod contracts, exact submitted identities, permissions and canonical policy comparison.
- `in-memory.ts`: Validated in-memory adapter with initialization, replacement and conflict handling.
- `http-route.ts`: Validated GET and PUT adapter for `/admin/filesystem/root-access`.
- `errors.ts`: Safe presentation of typed transport failures without exposing response bodies.
- `administration.test.ts`: Port and HTTP boundary checks.
