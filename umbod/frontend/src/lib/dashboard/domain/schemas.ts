import { z } from 'zod';

const capabilityMetadataSchema = z.object({
  key: z.string(),
  name: z.string(),
  description: z.string()
}).strict();

const catalogueToolOutputSchema = z.discriminatedUnion('status', [
  z.object({ status: z.literal('absent') }).strict(),
  z.object({ status: z.literal('present'), schema: z.record(z.string(), z.unknown()) }).strict()
]);

export const catalogueCapabilitySchema = z.discriminatedUnion('kind', [
  capabilityMetadataSchema.extend({
    kind: z.literal('tool'),
    input_schema: z.record(z.string(), z.unknown()),
    output_schema: catalogueToolOutputSchema
  }),
  capabilityMetadataSchema.extend({
    kind: z.enum(['prompt', 'resource', 'resource_template'])
  })
]);

export const catalogueConnectorSchema = z.object({
  connector_id: z.string(),
  kind: z.enum(['native', 'openapi', 'downstream_mcp']),
  display_name: z.string(),
  capability_description: z.string(),
  ownership: z.enum(['shared', 'personal']),
  capabilities: z.array(catalogueCapabilitySchema)
}).strict();

export const userCatalogueSchema = z.object({
  identity_key: z.string().min(1),
  personal_enabled: z.boolean(),
  connectors: z.array(catalogueConnectorSchema)
}).strict();

export type CatalogueCapability = z.infer<typeof catalogueCapabilitySchema>;
export type CatalogueConnector = z.infer<typeof catalogueConnectorSchema>;
export type UserCatalogue = z.infer<typeof userCatalogueSchema>;
