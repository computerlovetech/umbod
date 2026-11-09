import { HttpError, SchemaValidationError } from '$lib/admin/infrastructure/transport';
import type { NodeSharingApi } from '../api';
import { nodeAccessSchema, nodeAccessWriteSchema, replaceAccessSchema, sharingRecipientSchema, sharingRecipientSearchSchema, sharingRecipientSearchResultSchema, sharingRecipientTypeSchema, type SharingRecipientType, type NodeAccess, type ReplaceAccess, type SharingRecipient, type SharingRecipientSearchResult } from '../domain/sharing';

export class InMemoryNodeSharing implements NodeSharingApi {
  private readonly access = new Map<string, NodeAccess>();
  private recipients: SharingRecipient[] = [];

  configure = (access: NodeAccess, recipients: SharingRecipient[]): void => {
    this.access.set(access.node_id, nodeAccessSchema.parse(access));
    this.recipients = sharingRecipientSchema.array().parse(recipients);
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

  searchRecipients = async (id: string, query: string, recipientType?: SharingRecipientType, signal?: AbortSignal): Promise<SharingRecipientSearchResult> => {
    const parsed = sharingRecipientSearchSchema.safeParse({ query, recipient_type: recipientType });
    if (!parsed.success) throw new SchemaValidationError('outbound', parsed.error.issues);
    const access = await this.inspectAccess(id, parsed.data.recipient_type, signal);
    const normalizedQuery = this.normalizeSearchText(parsed.data.query);
    const matches = this.recipients.filter((recipient) =>
      (parsed.data.recipient_type === undefined || recipient.type === parsed.data.recipient_type)
      && !access.blocked_recipients.some((blocked) => blocked.type === recipient.type && (blocked.type === 'group' && recipient.type === 'group' ? blocked.group_id === recipient.group_id : blocked.type === 'user' && recipient.type === 'user' && blocked.user_id === recipient.user_id))
      && (this.normalizeSearchText(recipient.label).includes(normalizedQuery) || recipient.type === 'group' && this.normalizeSearchText(recipient.group_id).includes(normalizedQuery))
    );
    return sharingRecipientSearchResultSchema.parse({ recipients: matches.slice(0, 50), has_more: matches.length > 50 });
  };

  private normalizeSearchText(value: string): string { return value.trim().replace(/\s+/g, ' ').toLowerCase(); }

  replaceAccess = async (id: string, revision: string, body: ReplaceAccess, recipientType: SharingRecipientType): Promise<NodeAccess> => {
    sharingRecipientTypeSchema.parse(recipientType);
    const current = await this.inspectAccess(id);
    const parsed = replaceAccessSchema.parse(body);
    if (revision !== current.revision) throw new HttpError(412, 'Conflict', {});
    const grants = parsed.grants.map(({ recipient, permissions, recursive }) => {
      if (recipient.type !== recipientType || current.blocked_recipients.some((blocked) => JSON.stringify(blocked) === JSON.stringify(recipient))) throw new HttpError(422, 'Invalid recipient', {});
      const known = this.recipients.find((candidate) => candidate.type === recipient.type && (candidate.type === 'group' && recipient.type === 'group' ? candidate.group_id === recipient.group_id : candidate.type === 'user' && recipient.type === 'user' && candidate.user_id === recipient.user_id));
      if (!known) throw new HttpError(422, 'Invalid recipient', {});
      return { recipient: known, permissions, recursive };
    });
    const result = nodeAccessSchema.parse({ ...current, grants: [...current.grants.filter((grant) => grant.recipient.type !== recipientType), ...grants], revision: current.revision + '-next' });
    this.access.set(id, result);
    return nodeAccessWriteSchema.transform(({ node_id, revision, grants, blocked_recipients }) => ({ node_id, revision, grants, blocked_recipients })).parse({
      ...await this.inspectAccess(id, recipientType),
      visible_to: { type: 'unavailable' }
    });
  };
}
