import type { Transport } from '$lib/admin/infrastructure/transport';
import { directoryGroupsSchema, directoryQuerySchema, type DirectoryGroups, type DirectoryQuery } from './domain/schemas';
import type { IdentityGroupDirectory, IdentityObservation } from './port';

export class IdentityObservationsRoute implements IdentityObservation {
  constructor(private readonly transport: Transport) {}
  observe(): Promise<void> {
    return this.transport.request({ method: 'POST', path: '/me/identity-observations', requestBody: { kind: 'absent' } });
  }
}
export class IdentityDirectoryGroupsRoute implements IdentityGroupDirectory {
  constructor(private readonly transport: Transport) {}
  list(query: DirectoryQuery): Promise<DirectoryGroups> {
    const input = directoryQuerySchema.parse(query);
    const search = new URLSearchParams({ query: input.query, limit: String(input.limit) });
    return this.transport.request({ method: 'GET', path: `/admin/identity-directory/groups?${search}`, outputSchema: directoryGroupsSchema });
  }
}
