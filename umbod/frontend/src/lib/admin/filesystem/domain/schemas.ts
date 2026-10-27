import { z } from 'zod';

export const permissions = ['discover', 'read', 'write', 'delete', 'share'] as const;
export const permissionLabels: Record<Permission, string> = { discover: 'Browse root', read: 'Read', write: 'Create items', delete: 'Delete', share: 'Share' };
export const permissionSchema = z.enum(permissions);
export type Permission = z.infer<typeof permissionSchema>;
const exactGroupIdSchema = z.string().refine((value) => value.trim().length > 0, 'Enter a nonblank exact group ID');
export const groupGrantSchema = z.object({
  group_id: exactGroupIdSchema,
  permissions: z.array(permissionSchema).min(1).refine((values) => new Set(values).size === values.length)
}).strict();
export type GroupGrant = z.infer<typeof groupGrantSchema>;
const groupsSchema = z.array(groupGrantSchema).refine((groups) => new Set(groups.map((group) => group.group_id)).size === groups.length, 'Each exact group ID must be unique');
export const rootAccessSchema = z.object({
  status: z.enum(['uninitialized', 'ready', 'conflict']),
  revision: z.string(),
  groups: groupsSchema,
  blocked_group_ids: z.array(z.string())
}).strict();
export const replaceRootAccessSchema = z.object({ expected_revision: z.string(), groups: groupsSchema }).strict();
export type RootAccess = z.infer<typeof rootAccessSchema>;
export type ReplaceRootAccess = z.infer<typeof replaceRootAccessSchema>;
export function canonicalGroups(groups: GroupGrant[]): string {
  return JSON.stringify(groups.map((group) => ({ group_id: group.group_id, permissions: permissions.filter((permission) => group.permissions.includes(permission)) })).sort((left, right) => left.group_id.localeCompare(right.group_id)));
}
