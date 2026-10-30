import { z } from 'zod';

export const directoryQuerySchema = z.object({ query: z.string(), limit: z.number().int().min(1).max(100) });
export const observedGroupSchema = z.object({ value: z.string(), first_seen_at: z.iso.datetime({ offset: true }), last_seen_at: z.iso.datetime({ offset: true }) });
export const directoryGroupsSchema = z.object({ issuer: z.string(), claim: z.string(), groups: z.array(observedGroupSchema), has_more: z.boolean() });
export type DirectoryQuery = z.infer<typeof directoryQuerySchema>;
export type DirectoryGroups = z.infer<typeof directoryGroupsSchema>;
