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
const outboundGrantSchema = z.strictObject({ recipient: sharingRecipientTargetSchema, permissions: permissionsSchema });
const inboundGrantSchema = z.strictObject({ recipient: sharingRecipientSchema, permissions: permissionsSchema });
export const replaceAccessSchema = z.strictObject({ grants: z.array(outboundGrantSchema) }).refine((body) => new Set(body.grants.map(({ recipient }) => JSON.stringify(recipient))).size === body.grants.length);
export const nodeAccessSchema = z.strictObject({ node_id: nodeIdSchema, revision: sharingRevisionSchema, grants: z.array(inboundGrantSchema), blocked_recipients: z.array(sharingRecipientTargetSchema) });
export const nodeAccessWriteSchema = nodeAccessSchema.extend({ visible_to: nodeVisibilitySchema });
export type NodeAccessWrite = z.infer<typeof nodeAccessWriteSchema>;
export type SharingRecipientType = z.infer<typeof sharingRecipientTypeSchema>;
export const eligibleSharingGroupsSchema = z.strictObject({ groups: z.array(z.strictObject({ group_id: groupIdSchema, label: z.string(), description: z.string() })) });
export type SharingPermission = z.infer<typeof sharingPermissionSchema>;
export type NodeAccess = z.infer<typeof nodeAccessSchema>;
export type ReplaceAccess = z.infer<typeof replaceAccessSchema>;
export type SharingGroup = z.infer<typeof eligibleSharingGroupsSchema>['groups'][number];

export const sharingPermissions: ReadonlyArray<{ readonly value: SharingPermission; readonly label: string }> = [
  { value: 'discover', label: 'Discover' }, { value: 'read', label: 'Read' }, { value: 'write', label: 'Write' },
  { value: 'delete', label: 'Delete' }, { value: 'share', label: 'Manage sharing' }
];
