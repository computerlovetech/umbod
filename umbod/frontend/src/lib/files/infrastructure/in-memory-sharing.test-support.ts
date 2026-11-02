import { HttpError } from '$lib/admin/infrastructure/transport';
import type { NodeSharingApi } from '../api';
import { nodeAccessSchema, nodeAccessWriteSchema, replaceAccessSchema, eligibleSharingGroupsSchema, sharingRecipientTypeSchema, type SharingRecipientType, type NodeAccess, type ReplaceAccess, type SharingGroup } from '../domain/sharing';

export class InMemoryNodeSharing implements NodeSharingApi {
  private readonly access = new Map<string, NodeAccess>();
  private groups: SharingGroup[] = [];

  configure = (access: NodeAccess, groups: SharingGroup[]): void => {
    this.access.set(access.node_id, nodeAccessSchema.parse(access));
    this.groups = eligibleSharingGroupsSchema.parse({ groups }).groups;
  };

  available = (id: string): boolean => this.access.has(id);

  revoke = (id: string): void => { this.access.delete(id); };

  inspectAccess = async (id: string, recipientType?: SharingRecipientType, signal?: AbortSignal): Promise<NodeAccess> => {
    signal?.throwIfAborted();
    if (recipientType !== undefined) sharingRecipientTypeSchema.parse(recipientType);
    const access = this.access.get(id);
    if (!access) throw new HttpError(403, 'Forbidden', {});
    return nodeAccessSchema.parse({ ...access, grants: access.grants.filter((grant) => recipientType === undefined || grant.recipient.type === recipientType), blocked_recipients: access.blocked_recipients.filter((recipient) => recipientType === undefined || recipient.type === recipientType) });
  };

  listEligibleSharingGroups = async (id: string, signal?: AbortSignal): Promise<SharingGroup[]> => {
    const access = await this.inspectAccess(id, 'group', signal);
    const blocked = access.blocked_recipients.flatMap((recipient) => recipient.type === 'group' ? [recipient.group_id] : []);
    return eligibleSharingGroupsSchema.parse({ groups: this.groups.filter((group) => !blocked.includes(group.group_id)) }).groups;
  };

  replaceAccess = async (id: string, revision: string, body: ReplaceAccess, recipientType: SharingRecipientType): Promise<NodeAccess> => {
    sharingRecipientTypeSchema.parse(recipientType);
    const current = await this.inspectAccess(id);
    const parsed = replaceAccessSchema.parse(body);
    if (revision !== current.revision) throw new HttpError(412, 'Conflict', {});
    const grants = parsed.grants.map(({ recipient, permissions }) => {
      if (recipient.type !== recipientType || current.blocked_recipients.some((blocked) => JSON.stringify(blocked) === JSON.stringify(recipient))) throw new HttpError(422, 'Invalid recipient', {});
      const group = recipient.type === 'group' ? this.groups.find((candidate) => candidate.group_id === recipient.group_id) : undefined;
      if (recipient.type === 'group' && !group) throw new HttpError(422, 'Invalid group', {});
      const previous = current.grants.find((grant) => grant.recipient.type === recipient.type && (grant.recipient.type === 'group' && recipient.type === 'group' ? grant.recipient.group_id === recipient.group_id : grant.recipient.type === 'user' && recipient.type === 'user' && grant.recipient.user_id === recipient.user_id));
      return { recipient: { ...recipient, label: group?.label ?? previous?.recipient.label ?? (recipient.type === 'user' ? recipient.user_id : recipient.group_id) }, permissions };
    });
    const result = nodeAccessSchema.parse({ ...current, grants: [...current.grants.filter((grant) => grant.recipient.type !== recipientType), ...grants], revision: current.revision + '-next' });
    this.access.set(id, result);
    return nodeAccessWriteSchema.transform(({ node_id, revision, grants, blocked_recipients }) => ({ node_id, revision, grants, blocked_recipients })).parse({
      ...await this.inspectAccess(id, recipientType),
      visible_to: { type: 'unavailable' }
    });
  };
}
