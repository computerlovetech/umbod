import { SchemaValidationError, type Transport } from '$lib/admin/infrastructure/transport';
import type { NodeSharingApi } from '../api';
import { nodeIdSchema } from '../domain/schemas';
import { sharingRecipientTypeSchema, type SharingRecipientType, nodeAccessSchema, nodeAccessWriteSchema, replaceAccessSchema, sharingRevisionSchema, sharingRecipientSearchSchema, sharingRecipientSearchResultSchema, type NodeAccess, type ReplaceAccess, type SharingRecipientSearchResult } from '../domain/sharing';

export class NodeSharingRoute implements NodeSharingApi {
  constructor(private readonly transport: Transport) {}

  inspectAccess = (id: string, recipientType?: SharingRecipientType, signal?: AbortSignal): Promise<NodeAccess> =>
    this.transport.request({ method: 'GET', path: this.accessPath(id, recipientType), outputSchema: nodeAccessSchema, signal });

  searchRecipients = (id: string, query: string, recipientType?: SharingRecipientType, signal?: AbortSignal): Promise<SharingRecipientSearchResult> => {
    const parsed = sharingRecipientSearchSchema.safeParse({ query, recipient_type: recipientType });
    if (!parsed.success) throw new SchemaValidationError('outbound', parsed.error.issues);
    const parameters = new URLSearchParams({ query: parsed.data.query });
    if (parsed.data.recipient_type !== undefined) parameters.set('recipient_type', parsed.data.recipient_type);
    return this.transport.request({ method: 'GET', path: this.path(id) + '/recipients?' + parameters.toString(), outputSchema: sharingRecipientSearchResultSchema, signal });
  };

  replaceAccess = (id: string, revision: string, body: ReplaceAccess, recipientType: SharingRecipientType): Promise<NodeAccess> => {
    const parsed = sharingRevisionSchema.safeParse(revision);
    if (!parsed.success) throw new SchemaValidationError('outbound', parsed.error.issues);
    const scope = sharingRecipientTypeSchema.safeParse(recipientType);
    if (!scope.success) throw new SchemaValidationError('outbound', scope.error.issues);
    return this.transport.request({ method: 'PUT', path: this.accessPath(id, scope.data), body, inputSchema: replaceAccessSchema.refine((input) => input.grants.every((grant) => grant.recipient.type === recipientType)), conditionalHeaders: { 'If-Match': '"' + parsed.data + '"' }, outputSchema: nodeAccessWriteSchema.transform(({ node_id, revision, grants, blocked_recipients }) => ({ node_id, revision, grants, blocked_recipients })), redirect: 'error' });
  };

  private accessPath(id: string, recipientType: SharingRecipientType | undefined): string {
    if (recipientType === undefined) return this.path(id);
    const parsed = sharingRecipientTypeSchema.safeParse(recipientType);
    if (!parsed.success) throw new SchemaValidationError('outbound', parsed.error.issues);
    return this.path(id) + '?' + new URLSearchParams({ recipient_type: parsed.data }).toString();
  }

  private path(id: string): string { return '/me/filesystem/nodes/' + nodeIdSchema.parse(id) + '/access'; }
}
