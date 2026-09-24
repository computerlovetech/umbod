# Admin Infrastructure

**Module responsibility:** Shared HTTP transport and composition for Umbod administration APIs.

**Read when working with:** Browser or server request execution, transport behavior, or authentication forwarding. Feature-specific payload schemas live in the parent module's `*-api.ts` files.

## Modules

### `transport.ts`

**Read when working with:** Shared request execution and validated transport contracts.

### `server-api.ts`

**Read when working with:** Server-side administration API access.

### `browser-request.ts`

**Read when working with:** Browser-side administration requests.

### `schema.ts`

**Read when working with:** Schema helpers shared by feature-specific API adapters.
