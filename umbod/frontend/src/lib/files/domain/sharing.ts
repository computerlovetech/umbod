import { z } from 'zod';
import { nodeIdSchema } from './schemas';

export const sharingRevisionSchema = z.string().regex(/^[\x21\x23-\x2b\x2d-\x7e]+$/);
export const sharingPermissionSchema = z.enum(['discover', 'read', 'write', 'delete', 'share']);
const groupIdSchema = z.string().min(1);
const permissionsSchema = z.array(sharingPermissionSchema).nonempty().refine((values) => new Set(values).size === values.length);
const outboundGroupSchema = z.strictObject({ group_id: groupIdSchema, permissions: permissionsSchema });
const inboundGroupSchema = z.strictObject({ group_id: groupIdSchema, permissions: permissionsSchema });
export const replaceAccessSchema = z.strictObject({ groups: z.array(outboundGroupSchema) }).refine((body) => new Set(body.groups.map((group) => group.group_id)).size === body.groups.length);
export const nodeAccessSchema = z.strictObject({ node_id: nodeIdSchema, revision: sharingRevisionSchema, groups: z.array(inboundGroupSchema), blocked_group_ids: z.array(groupIdSchema) });
export const eligibleSharingGroupsSchema = z.strictObject({ groups: z.array(z.strictObject({ group_id: groupIdSchema, label: z.string(), description: z.string() })) });
export type SharingPermission = z.infer<typeof sharingPermissionSchema>;
export type NodeAccess = z.infer<typeof nodeAccessSchema>;
export type ReplaceAccess = z.infer<typeof replaceAccessSchema>;
export type SharingGroup = z.infer<typeof eligibleSharingGroupsSchema>['groups'][number];

export const sharingPermissions: ReadonlyArray<{ readonly value: SharingPermission; readonly label: string }> = [
  { value: 'discover', label: 'Discover' }, { value: 'read', label: 'Read' }, { value: 'write', label: 'Write' },
  { value: 'delete', label: 'Delete' }, { value: 'share', label: 'Manage sharing' }
];
