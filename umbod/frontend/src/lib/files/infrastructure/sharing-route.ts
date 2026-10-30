import { SchemaValidationError, type Transport } from '$lib/admin/infrastructure/transport';
import type { NodeSharingApi } from '../api';
import { nodeIdSchema } from '../domain/schemas';
import { nodeAccessSchema, replaceAccessSchema, sharingRevisionSchema, eligibleSharingGroupsSchema, type NodeAccess, type ReplaceAccess, type SharingGroup } from '../domain/sharing';

export class NodeSharingRoute implements NodeSharingApi {
  constructor(private readonly transport: Transport) {}

  inspectAccess = (id: string, signal?: AbortSignal): Promise<NodeAccess> =>
    this.transport.request({ method: 'GET', path: this.path(id), outputSchema: nodeAccessSchema, signal });

  listEligibleSharingGroups = async (id: string, signal?: AbortSignal): Promise<SharingGroup[]> => {
    const result = await this.transport.request({ method: 'GET', path: this.path(id) + '/eligible-groups', outputSchema: eligibleSharingGroupsSchema, signal });
    return result.groups;
  };

  replaceAccess = (id: string, revision: string, body: ReplaceAccess): Promise<NodeAccess> => {
    const parsed = sharingRevisionSchema.safeParse(revision);
    if (!parsed.success) throw new SchemaValidationError('outbound', parsed.error.issues);
    return this.transport.request({ method: 'PUT', path: this.path(id), body, inputSchema: replaceAccessSchema, conditionalHeaders: { 'If-Match': '"' + parsed.data + '"' }, outputSchema: nodeAccessSchema, redirect: 'error' });
  };

  private path(id: string): string { return '/me/filesystem/nodes/' + nodeIdSchema.parse(id) + '/access'; }
}
