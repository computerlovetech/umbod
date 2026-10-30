import { HttpError } from '$lib/admin/infrastructure/transport';
import type { NodeSharingApi } from '../api';
import { nodeAccessSchema, replaceAccessSchema, eligibleSharingGroupsSchema, type NodeAccess, type ReplaceAccess, type SharingGroup } from '../domain/sharing';

export class InMemoryNodeSharing implements NodeSharingApi {
  private readonly access = new Map<string, NodeAccess>();
  private groups: SharingGroup[] = [];

  configure = (access: NodeAccess, groups: SharingGroup[]): void => {
    this.access.set(access.node_id, nodeAccessSchema.parse(access));
    this.groups = eligibleSharingGroupsSchema.parse({ groups }).groups;
  };

  revoke = (id: string): void => { this.access.delete(id); };

  inspectAccess = async (id: string, signal?: AbortSignal): Promise<NodeAccess> => {
    signal?.throwIfAborted();
    const access = this.access.get(id);
    if (!access) throw new HttpError(403, 'Forbidden', {});
    return nodeAccessSchema.parse(access);
  };

  listEligibleSharingGroups = async (id: string, signal?: AbortSignal): Promise<SharingGroup[]> => {
    const access = await this.inspectAccess(id, signal);
    return eligibleSharingGroupsSchema.parse({ groups: this.groups.filter((group) => !access.blocked_group_ids.includes(group.group_id)) }).groups;
  };

  replaceAccess = async (id: string, revision: string, body: ReplaceAccess): Promise<NodeAccess> => {
    const current = await this.inspectAccess(id);
    const parsed = replaceAccessSchema.parse(body);
    if (revision !== current.revision) throw new HttpError(412, 'Conflict', {});
    if (parsed.groups.some((group) => current.blocked_group_ids.includes(group.group_id) || !this.groups.some((candidate) => candidate.group_id === group.group_id))) throw new HttpError(422, 'Invalid group', {});
    const result = nodeAccessSchema.parse({ ...current, groups: parsed.groups, revision: current.revision + '-next' });
    this.access.set(id, result);
    return nodeAccessSchema.parse(result);
  };
}
