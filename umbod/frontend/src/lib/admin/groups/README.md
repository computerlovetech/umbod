# Shared group catalogue

- `port.ts`: `GroupCatalogue` list, idempotent registration and deletion operations independent of access grants.
- `domain/schemas.ts`: Separate observed catalogue and registration request schemas. New group IDs must be nonblank; observations preserve legacy IDs. Values are never trimmed or normalized.
- `in-memory.ts`: Validated in-memory catalogue with exact-key idempotence and isolated snapshots.
- `http-route.ts`: Shared `/admin/groups` GET and JSON-body POST/DELETE adapter. Body-based deletion preserves exact IDs, including URL dot segments. Referenced-group deletion conflicts remain transport errors; the backend owns reference checks across connector, capability and filesystem grants.
- `catalogue.test.ts`: Port behavior, HTTP boundary validation, deletion conflicts and shared composite wiring.

`AdminApi.groups` and the connector permissions compatibility delegates use the same route. Registration creates no permissions and no identity-provider membership. Filesystem grants remain independently qualified by explicit issuer and exact group value.
