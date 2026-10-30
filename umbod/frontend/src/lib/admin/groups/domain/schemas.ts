import { z } from 'zod';

export const groupIdSchema = z.string().refine((value) => value.trim().length > 0, 'Enter a nonblank exact group ID');
export const groupMetadataSchema = z.object({ label: z.string().trim().min(1).max(200), description: z.string().max(2000) }).strict();
export const catalogueGroupSchema = z.object({ group_id: z.string(), label: z.string(), description: z.string(), revision: z.number().int().positive() }).strict();
export const createGroupSchema = groupMetadataSchema.extend({ group_id: groupIdSchema }).strict();
export const updateGroupSchema = groupMetadataSchema.extend({ group_id: z.string(), expected_revision: z.number().int().positive() }).strict();
export type CreateGroup = z.infer<typeof createGroupSchema>;
export type UpdateGroup = z.infer<typeof updateGroupSchema>;
export const groupCatalogueResponseSchema = z.object({ groups: z.array(catalogueGroupSchema) }).strict();
export const deleteGroupSchema = z.object({ group_id: z.string() }).strict();
export const registerGroupSchema = z.object({ group_id: groupIdSchema }).strict();
export type CatalogueGroup = z.infer<typeof catalogueGroupSchema>;
