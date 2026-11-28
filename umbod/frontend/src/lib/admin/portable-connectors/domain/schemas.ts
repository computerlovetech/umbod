import { z } from 'zod';

export const portableConnectorSummarySchema = z.object({
  connector_id: z.uuid(),
  name: z.string(),
  description: z.string(),
  status: z.literal('inactive'),
  configured: z.boolean()
});

export const portableConnectorListSchema = z.object({
  connectors: z.array(portableConnectorSummarySchema)
});

const portableConnectorFieldSchema = z.object({
  name: z.string(),
  label: z.string(),
  required: z.boolean(),
  min_length: z.int().nonnegative(),
  max_length: z.int().nonnegative(),
  choices: z.array(z.string())
});

export const portableConnectorConfigurationSchema = z.object({
  connector: portableConnectorSummarySchema,
  fields: z.array(portableConnectorFieldSchema),
  configuration: z.record(z.string(), z.string()).nullable()
});

export const replacePortableConfigurationSchema = z.strictObject({
  configuration: z.record(z.string(), z.string())
});

export type PortableConnectorSummary = z.infer<typeof portableConnectorSummarySchema>;
export type PortableConnectorList = z.infer<typeof portableConnectorListSchema>;
export type PortableConnectorField = z.infer<typeof portableConnectorFieldSchema>;
export type PortableConnectorConfiguration = z.infer<typeof portableConnectorConfigurationSchema>;
export type ReplacePortableConfiguration = z.infer<typeof replacePortableConfigurationSchema>;
