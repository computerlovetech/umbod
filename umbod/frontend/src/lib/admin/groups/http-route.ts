import { groupCatalogueResponseSchema, registerGroupSchema, type CatalogueGroup } from './domain/schemas';
import type { GroupCatalogue } from './port';
import type { Transport } from '../infrastructure/transport';

export class GroupsRoute implements GroupCatalogue {
  constructor(private readonly transport: Transport) {}
  async list(): Promise<CatalogueGroup[]> {
    const response = await this.transport.request({ method: 'GET', path: '/admin/groups', outputSchema: groupCatalogueResponseSchema });
    return response.groups;
  }
  register(groupId: string): Promise<void> {
    return this.transport.request({ method: 'POST', path: '/admin/groups', body: { group_id: groupId }, inputSchema: registerGroupSchema });
  }
  delete(groupId: string): Promise<void> {
    return this.transport.request({ method: 'DELETE', path: '/admin/groups', body: { group_id: groupId }, inputSchema: registerGroupSchema });
  }
}
