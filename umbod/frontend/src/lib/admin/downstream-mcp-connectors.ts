import { z } from 'zod';
import { capabilityDescriptionOverrideSchema } from './capability-descriptions';

export const downstreamMcpPublicPathPrefix = '/mcp/proxies/';
const reservedProxySlugs = new Set(['mcp', 'proxies', 'oauth', 'health', 'assets', '.well-known']);
export const downstreamMcpProxySlugSchema = z.string().regex(/^[a-z0-9][a-z0-9-]{0,62}$/).refine((slug) => !reservedProxySlugs.has(slug), 'Proxy slug is reserved');
export const downstreamMcpPublicPathSchema = z.string().refine(
  (path) => path.startsWith(downstreamMcpPublicPathPrefix) && downstreamMcpProxySlugSchema.safeParse(path.slice(downstreamMcpPublicPathPrefix.length)).success,
  'Public path must use /mcp/proxies/{slug}'
);

export const downstreamMcpCapabilityDescriptionSchema = z.string().trim().min(1).max(300).refine((value) => !/[\u0000-\u001f\u007f-\u009f]/.test(value), 'Capability description must be plain text');
export const downstreamMcpToolNamePrefixSchema = z.string().trim().regex(/^[a-zA-Z0-9_-]+$/);

export const downstreamMcpAuthModeSchema = z.enum(['none', 'static_bearer']);
const downstreamMcpResponseAuthModeSchema = z.enum(['none', 'static_bearer', 'oauth']);
export const downstreamMcpHeaderTypeSchema = z.enum(['bearer', 'basic', 'custom']);
export const downstreamMcpCustomHeaderNameSchema = z.string().min(1).regex(/^[!#$%&'*+.^_`|~0-9A-Za-z-]+$/).refine((value) => value.toLowerCase() !== 'authorization', 'Custom header name must not be Authorization');
export const downstreamMcpHealthSchema = z.object({
  status: z.enum(['unknown', 'healthy', 'unhealthy']),
  checked_at: z.string().nullable(),
  reason: z.string().nullable()
}).strict();
export const downstreamMcpConnectorSchema = z.object({
  connector_id: z.string().min(1),
  display_name: z.string().min(1),
  tool_name_prefix: downstreamMcpToolNamePrefixSchema,
  icon_url: z.string(),
  capability_description: downstreamMcpCapabilityDescriptionSchema,
  base_capability_description: downstreamMcpCapabilityDescriptionSchema,
  effective_capability_description: downstreamMcpCapabilityDescriptionSchema,
  capability_description_override: capabilityDescriptionOverrideSchema,
  endpoint_url: z.string().url(),
  public_path: downstreamMcpPublicPathSchema,
  public_url: z.string().url(),
  auth_mode: downstreamMcpAuthModeSchema,
  header_type: downstreamMcpHeaderTypeSchema,
  custom_header_name: z.string().nullable(),
  credential_configured: z.boolean(),
  publication_status: z.enum(['published', 'unpublished']),
  health: downstreamMcpHealthSchema
}).strict();
export const downstreamMcpConnectorSummarySchema = z.object({
  connector_id: z.string().min(1),
  display_name: z.string().min(1),
  icon_url: z.string(),
  auth_mode: downstreamMcpResponseAuthModeSchema,
  publication_status: z.enum(['published', 'unpublished']),
  health: downstreamMcpHealthSchema
}).strict();
export const downstreamMcpConnectorListSchema = z.object({
  connectors: z.array(downstreamMcpConnectorSummarySchema)
}).strict();
const createMetadataSchema = z.object({
  display_name: z.string().min(1),
  tool_name_prefix: downstreamMcpToolNamePrefixSchema,
  capability_description: downstreamMcpCapabilityDescriptionSchema,
  public_path: downstreamMcpPublicPathSchema
}).strict();
const validateStaticHeaderConfiguration = (value: { header_type: 'bearer' | 'basic' | 'custom'; custom_header_name: string | null }, context: z.RefinementCtx): void => {
  if (value.header_type === 'custom') {
    const result = downstreamMcpCustomHeaderNameSchema.safeParse(value.custom_header_name);
    if (!result.success) context.addIssue({ code: 'custom', path: ['custom_header_name'], message: 'A valid custom header name is required' });
  } else if (value.custom_header_name !== null) {
    context.addIssue({ code: 'custom', path: ['custom_header_name'], message: 'Custom header name is forbidden' });
  }
};
const createConfigurationSchema = z.union([
  z.object({ auth_mode: z.literal('none'), endpoint_url: z.string().url(), bearer_token: z.null(), header_type: z.null().optional(), custom_header_name: z.null().optional() }).strict(),
  z.object({ auth_mode: z.literal('static_bearer'), endpoint_url: z.string().url(), bearer_token: z.string().min(1), header_type: downstreamMcpHeaderTypeSchema.default('bearer'), custom_header_name: z.string().nullable().default(null) }).strict().superRefine(validateStaticHeaderConfiguration)
]);
const configurationSchema = z.union([
  z.object({ auth_mode: z.literal('none'), endpoint_url: z.string().url(), bearer_token: z.null(), header_type: z.null().optional(), custom_header_name: z.null().optional() }).strict(),
  z.object({ auth_mode: z.literal('static_bearer'), endpoint_url: z.string().url(), bearer_token: z.string().nullable(), header_type: downstreamMcpHeaderTypeSchema.default('bearer'), custom_header_name: z.string().nullable().default(null) }).strict().superRefine(validateStaticHeaderConfiguration)
]);
const initialCapabilityDescriptionOverrideSchema = z.discriminatedUnion('state', [
  z.object({ state: z.literal('system') }).strict(),
  z.object({ state: z.literal('overridden'), description: downstreamMcpCapabilityDescriptionSchema }).strict()
]);
export const downstreamMcpConnectorCreateInputSchema = z.object({
  metadata: createMetadataSchema,
  configuration: createConfigurationSchema,
  capability_description_override: initialCapabilityDescriptionOverrideSchema.default({ state: 'system' })
}).strict();
export const downstreamMcpConnectorMetadataPatchSchema = z.object({ display_name: z.string().min(1).optional(), tool_name_prefix: downstreamMcpToolNamePrefixSchema.optional(), capability_description: downstreamMcpCapabilityDescriptionSchema.optional(), public_path: downstreamMcpPublicPathSchema.optional() }).strict().refine((value) => Object.keys(value).length > 0, 'at least one metadata field is required');
export const downstreamMcpConnectorConfigurationInputSchema = configurationSchema;
export const downstreamMcpConnectorConfigurationSchema = z.object({ endpoint_url: z.string().url(), auth_mode: downstreamMcpAuthModeSchema, header_type: downstreamMcpHeaderTypeSchema, custom_header_name: z.string().nullable(), credential_configured: z.boolean() }).strict();
export const downstreamMcpToolSchema = z.object({
  name: z.string().min(1), title: z.string().min(1), description: z.string(), input_schema: z.record(z.string(), z.unknown()), output_schema: z.record(z.string(), z.unknown()).nullable(), activation_status: z.enum(['enabled', 'disabled'])
}).strict();
export const downstreamMcpToolListSchema = z.object({
  discovered_at: z.string().nullable(), tools: z.array(downstreamMcpToolSchema)
}).strict();
export const downstreamMcpPublicationSchema = z.object({
  connector_id: z.string().min(1), publication_status: z.enum(['published', 'unpublished'])
}).strict();
const downstreamMcpToolActivationBatchRequestItemSchema = z.object({
  tool_id: z.string().min(1), activation_status: z.enum(['enabled', 'disabled']).optional(), invocation_mode: z.enum(['direct', 'ask']).optional(), expected_policy_revision: z.number().int().nonnegative().optional()
}).strict().refine((tool) => Boolean(tool.activation_status || tool.invocation_mode), 'at least one change is required').refine((tool) => Boolean(tool.invocation_mode) === (tool.expected_policy_revision !== undefined), 'invocation_mode and expected_policy_revision must be provided together');
const downstreamMcpToolActivationBatchResponseItemSchema = z.object({
  tool_id: z.string().min(1), activation_status: z.enum(['enabled', 'disabled']), invocation_mode: z.enum(['direct', 'ask']), policy_revision: z.number().int().nonnegative()
}).strict();
export const downstreamMcpToolActivationBatchRequestSchema = z.object({
  tools: z.array(downstreamMcpToolActivationBatchRequestItemSchema).min(1)
}).strict().refine(({ tools }) => new Set(tools.map((tool) => tool.tool_id)).size === tools.length, 'tool_id values must be unique');
export const downstreamMcpToolActivationBatchResponseSchema = z.object({
  connector_id: z.string().min(1), tools: z.array(downstreamMcpToolActivationBatchResponseItemSchema)
}).strict();

export type DownstreamMcpConnector = z.infer<typeof downstreamMcpConnectorSchema>;
export type DownstreamMcpConnectorSummary = z.infer<typeof downstreamMcpConnectorSummarySchema>;
export type DownstreamMcpConnectorCreateInput = z.infer<typeof downstreamMcpConnectorCreateInputSchema>;
export type DownstreamMcpConnectorMetadataPatch = z.infer<typeof downstreamMcpConnectorMetadataPatchSchema>;
export type DownstreamMcpConnectorConfigurationInput = z.infer<typeof downstreamMcpConnectorConfigurationInputSchema>;
export type DownstreamMcpTool = z.infer<typeof downstreamMcpToolSchema>;
export type DownstreamMcpToolList = z.infer<typeof downstreamMcpToolListSchema>;
export type DownstreamMcpToolActivationBatchRequest = z.infer<typeof downstreamMcpToolActivationBatchRequestSchema>;
export type DownstreamMcpToolActivationBatchResponse = z.infer<typeof downstreamMcpToolActivationBatchResponseSchema>;
