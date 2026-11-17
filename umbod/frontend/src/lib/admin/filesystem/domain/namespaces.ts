import { z } from 'zod';
import { fileNameSchema } from '#lib/files/domain/schemas.js';

export const namespaceGroupSchema = z.strictObject({
  group_id: z.string().refine((value) => value.trim().length > 0),
  access: z.enum(['read', 'read_write'])
});
const groupsSchema = z.array(namespaceGroupSchema).refine((groups) => new Set(groups.map((group) => group.group_id)).size === groups.length);
export const createNamespaceSchema = z.strictObject({ name: fileNameSchema.max(255), groups: groupsSchema, description: z.string().optional() });
export const updateNamespaceSchema = z.strictObject({
  expected_revision: z.number().int().positive(), name: fileNameSchema.max(255), groups: groupsSchema,
  description: z.string().optional(), expected_root_revision: z.number().int().positive().optional()
}).refine((input) => (input.description === undefined) === (input.expected_root_revision === undefined), {
  message: 'Description and root revision must be supplied together.', path: ['expected_root_revision']
});
export const sharedNamespaceSchema = z.strictObject({
  id: z.uuid(), root_node_id: z.uuid(), name: z.string(),
  revision: z.number().int().positive(), root_revision: z.number().int().positive(), description: z.string(), groups: groupsSchema
});
export const sharedNamespacesSchema = z.strictObject({ namespaces: z.array(sharedNamespaceSchema) });
export type NamespaceGroup = z.infer<typeof namespaceGroupSchema>;
export type SharedNamespace = z.infer<typeof sharedNamespaceSchema>;
export type CreateNamespace = z.infer<typeof createNamespaceSchema>;
export type UpdateNamespace = z.infer<typeof updateNamespaceSchema>;
