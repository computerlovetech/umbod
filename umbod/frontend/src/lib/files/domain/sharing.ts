import { z } from 'zod';
import { nodeIdSchema, nodeVisibilitySchema } from './schemas';

export const sharingRevisionSchema = z.string().regex(/^[\x21\x23-\x2b\x2d-\x7e]+$/);
export const sharingPermissionSchema = z.enum(['discover', 'read', 'write', 'delete', 'share']);
const groupIdSchema = z.string().min(1);
const permissionsSchema = z.array(sharingPermissionSchema).nonempty().refine((values) => new Set(values).size === values.length);
export const sharingRecipientTypeSchema = z.enum(['group', 'user']);
export const sharingRecipientTargetSchema = z.discriminatedUnion('type', [
  z.strictObject({ type: z.literal('group'), group_id: groupIdSchema }),
  z.strictObject({ type: z.literal('user'), user_id: z.string().min(1) })
]);
export const sharingRecipientSchema = z.discriminatedUnion('type', [
  z.strictObject({ type: z.literal('group'), group_id: groupIdSchema, label: z.string() }),
  z.strictObject({ type: z.literal('user'), user_id: z.string().min(1), label: z.string() })
]);
const outboundGrantSchema = z.strictObject({ recipient: sharingRecipientTargetSchema, permissions: permissionsSchema, recursive: z.boolean() });
const inboundGrantSchema = z.strictObject({ recipient: sharingRecipientSchema, permissions: permissionsSchema, recursive: z.boolean() });
export const replaceAccessSchema = z.strictObject({ grants: z.array(outboundGrantSchema) }).refine((body) => new Set(body.grants.map(({ recipient }) => JSON.stringify(recipient))).size === body.grants.length);
export const nodeAccessSchema = z.strictObject({ node_id: nodeIdSchema, revision: sharingRevisionSchema, grants: z.array(inboundGrantSchema), blocked_recipients: z.array(sharingRecipientTargetSchema) });
export const nodeAccessWriteSchema = nodeAccessSchema.extend({ visible_to: nodeVisibilitySchema });
export type NodeAccessWrite = z.infer<typeof nodeAccessWriteSchema>;
export type SharingRecipientType = z.infer<typeof sharingRecipientTypeSchema>;
export const sharingRecipientSearchQuerySchema = z.string().trim().min(1).max(200);
export const sharingRecipientSearchSchema = z.strictObject({ query: sharingRecipientSearchQuerySchema, recipient_type: sharingRecipientTypeSchema.optional() });
export const sharingRecipientSearchResultSchema = z.strictObject({ recipients: z.array(sharingRecipientSchema), has_more: z.boolean() });
export type SharingRecipient = z.infer<typeof sharingRecipientSchema>;
export type SharingRecipientTarget = z.infer<typeof sharingRecipientTargetSchema>;
export type SharingRecipientSearchResult = z.infer<typeof sharingRecipientSearchResultSchema>;
export type SharingPermission = z.infer<typeof sharingPermissionSchema>;
export type NodeAccess = z.infer<typeof nodeAccessSchema>;
export type ReplaceAccess = z.infer<typeof replaceAccessSchema>;

export const sharingPermissions: ReadonlyArray<{ readonly value: SharingPermission; readonly label: string }> = [
  { value: 'discover', label: 'Discover' }, { value: 'read', label: 'Read' }, { value: 'write', label: 'Write' },
  { value: 'delete', label: 'Delete' }, { value: 'share', label: 'Manage sharing' }
];
