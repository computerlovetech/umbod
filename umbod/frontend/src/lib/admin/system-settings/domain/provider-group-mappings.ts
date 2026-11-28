import { z } from 'zod';

const literalString = z.string().refine((value): boolean => /[^\p{White_Space}\u001c-\u001f]/u.test(value), 'Must not be blank');

const providerGroupMappingSchema = z.strictObject({
  external_value: literalString,
  group_id: literalString
});

export const providerGroupMappingListSchema = z.array(providerGroupMappingSchema).superRefine((mappings, context): void => {
  const seen = new Set<string>();
  mappings.forEach(({ external_value, group_id }, index): void => {
    const row = JSON.stringify([external_value, group_id]);
    if (seen.has(row)) context.addIssue({ code: 'custom', path: [index], message: 'Remove duplicate mappings before saving.' });
    seen.add(row);
  });
});

export const providerGroupMappingsSchema = z.discriminatedUnion('source', [
  z.strictObject({ source: z.literal('built_in_default'), mappings: z.tuple([]) }),
  z.strictObject({ source: z.literal('admin_override'), mappings: providerGroupMappingListSchema })
]);

export const providerGroupMappingsPatchSchema = z.discriminatedUnion('operation', [
  z.strictObject({ operation: z.literal('set'), mappings: providerGroupMappingListSchema }),
  z.strictObject({ operation: z.literal('reset') })
]);

export type ProviderGroupMapping = z.infer<typeof providerGroupMappingSchema>;
export type ProviderGroupMappings = z.infer<typeof providerGroupMappingsSchema>;
export type ProviderGroupMappingsPatch = z.infer<typeof providerGroupMappingsPatchSchema>;
