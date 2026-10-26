import { z } from 'zod';

export const permissions = ['discover', 'read', 'write', 'delete', 'share'] as const;
export const permissionLabels: Record<Permission, string> = { discover: 'Browse root', read: 'Read', write: 'Create items', delete: 'Delete', share: 'Share' };
export const permissionSchema = z.enum(permissions);
export type Permission = z.infer<typeof permissionSchema>;
const exactIdentitySchema = z.string().refine((value) => value.trim().length > 0, 'Enter a nonblank exact identity');
export const groupGrantSchema = z.object({
  issuer: exactIdentitySchema,
  group_id: exactIdentitySchema,
  permissions: z.array(permissionSchema).min(1).refine((values) => new Set(values).size === values.length)
}).strict();
export type GroupGrant = z.infer<typeof groupGrantSchema>;
export const observedGroupPolicySchema = z.object({
  issuer: z.string(),
  group_id: z.string(),
  permissions: z.array(permissionSchema)
}).strict();
export type ObservedGroupPolicy = z.infer<typeof observedGroupPolicySchema>;
const groupsSchema = z.array(groupGrantSchema).refine((groups) => new Set(groups.map((group) => JSON.stringify([group.issuer, group.group_id]))).size === groups.length, 'Each issuer and group ID pair must be unique');
export const rootAccessSchema = z.object({
  root_id: z.string().uuid(),
  status: z.enum(['uninitialized', 'ready', 'conflict']),
  revision: z.string(),
  groups: z.array(observedGroupPolicySchema),
  unmanaged_groups: z.array(observedGroupPolicySchema),
  suggested_issuer: z.string(),
  group_claim: z.string()
}).strict();
export const replaceRootAccessSchema = z.object({ expected_revision: z.string(), groups: groupsSchema }).strict();
export type RootAccess = z.infer<typeof rootAccessSchema>;
export type ReplaceRootAccess = z.infer<typeof replaceRootAccessSchema>;
export function canonicalGroups(groups: ObservedGroupPolicy[]): string {
  return JSON.stringify(groups.map((group) => ({ issuer: group.issuer, group_id: group.group_id, permissions: permissions.filter((permission) => group.permissions.includes(permission)) })).sort((left, right) => JSON.stringify([left.issuer, left.group_id]).localeCompare(JSON.stringify([right.issuer, right.group_id]))));
}
