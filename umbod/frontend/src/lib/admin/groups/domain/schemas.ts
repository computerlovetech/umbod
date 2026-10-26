import { z } from 'zod';

export const groupIdSchema = z.string().refine((value) => value.trim().length > 0, 'Enter a nonblank exact group ID');
export const catalogueGroupSchema = z.object({ group_id: z.string() }).strict();
export const groupCatalogueResponseSchema = z.object({ groups: z.array(catalogueGroupSchema) }).strict();
export const registerGroupSchema = z.object({ group_id: groupIdSchema }).strict();
export type CatalogueGroup = z.infer<typeof catalogueGroupSchema>;
