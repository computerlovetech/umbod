import { z } from 'zod';

export const catalogueCapabilitySchema = z.object({
  kind: z.enum(['tool', 'prompt', 'resource', 'resource_template']),
  key: z.string(),
  name: z.string(),
  description: z.string()
}).strict();

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
