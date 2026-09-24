import { z } from 'zod';
import { connectorToolOutputSchemaStateSchema, type ConnectorToolParameter } from './connectors';
import { normalizeDeclaredToolOutputSchema, type ToolOutputSchemaState } from './tool-output-schema';
import { mapJsonSchemaToConnectorToolParameters } from './json-schema-tool-parameters';
import { capabilityDescriptionOverrideSchema } from './capability-descriptions';

export const OPEN_API_CATALOG_FILE_MAX_BYTES = 10 * 1024 * 1024;

export const openApiConnectorPublicationStatusSchema = z.enum(['unconfigured', 'draft', 'published', 'unpublished']);
export const openApiAvailableActionSchema = z.enum(['import', 'publish', 'unpublish']);
export const openApiPublicationResultSchema = z.enum(['published', 'unpublished']);
export const openApiToolActivationStatusSchema = z.enum(['enabled', 'disabled']);

export const openApiConnectorSchema = z.object({
  connector_id: z.string().min(1),
  display_name: z.string().min(1),
  tool_name_prefix: z.string().regex(/^[a-zA-Z0-9_-]+$/),
  capability_description: z.string().trim().min(1).max(300),
  base_capability_description: z.string().trim().min(1).max(300),
  effective_capability_description: z.string().trim().min(1).max(300),
  capability_description_override: capabilityDescriptionOverrideSchema,
  created_at: z.string().min(1),
  updated_at: z.string().min(1),
  publication_status: openApiConnectorPublicationStatusSchema,
  available_actions: z.array(openApiAvailableActionSchema)
}).strict();

export const openApiConnectorSummarySchema = z.object({
  connector_id: z.string().min(1),
  display_name: z.string().min(1),
  publication_status: openApiConnectorPublicationStatusSchema,
  available_actions: z.array(openApiAvailableActionSchema)
}).strict();

export const openApiConnectorListResponseSchema = z.object({
  connectors: z.array(openApiConnectorSummarySchema).max(1000)
}).strict();

export const capabilityDescriptionSchema = z.string().trim().min(1).max(300);
export const toolNamePrefixSchema = z.string().trim().regex(/^[a-zA-Z0-9_-]+$/);
export const createOpenApiConnectorRequestSchema = z.object({
  display_name: z.string().trim().min(1).max(200),
  tool_name_prefix: toolNamePrefixSchema,
  capability_description: capabilityDescriptionSchema
}).strict();
export const openApiCatalogImportResponseSchema = z.object({
  connector_id: z.string().min(1),
  catalog_id: z.string().min(1),
  operation_ids: z.array(z.string()),
  approved_hosts: z.array(z.string()),
  selected_server_url: z.string().min(1),
  imported_at: z.string().min(1)
}).strict();
export const openApiGrantConflictDetailSchema = z.object({
  code: z.literal('openapi_operation_grants_conflict'),
  connector_id: z.string().min(1),
  removed_operation_ids: z.array(z.string().min(1)),
  affected_group_ids: z.array(z.string().min(1))
});
export const openApiGrantConflictResponseSchema = z.object({ detail: openApiGrantConflictDetailSchema });
export const approvedHostnameSchema = z.string().trim().toLowerCase().min(1).max(253).regex(/^(?=.{1,253}$)(?!-)(?:[a-z0-9-]{1,63}\.)*[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/);
export const importOpenApiCatalogFileMetadataSchema = z.object({ approved_hosts: z.array(approvedHostnameSchema) });
export const importOpenApiCatalogUrlRequestSchema = z.object({
  url: z.string().trim().url().refine((value) => {
    const parsed = new URL(value);
    return parsed.protocol === 'https:' && parsed.username === '' && parsed.password === '';
  }, 'Use an HTTPS URL without embedded credentials')
});
export const importOpenApiCatalogDocumentRequestSchema = z.object({
  document: z.record(z.string(), z.unknown()),
  approved_hosts: z.array(approvedHostnameSchema).min(1)
}).strict();
export const openApiOperationToolSchema = z.object({
  operation_id: z.string().min(1),
  method: z.string().min(1),
  path: z.string(),
  summary: z.string(),
  description: z.string(),
  activation_status: openApiToolActivationStatusSchema,
  parameters: z.record(z.string(), z.unknown())
}).and(connectorToolOutputSchemaStateSchema);
export const openApiOperationToolListResponseSchema = z.object({
  tools: z.array(openApiOperationToolSchema)
}).strict();
const openApiToolActivationBatchRequestItemSchema = z.object({
  tool_id: z.string().min(1), activation_status: openApiToolActivationStatusSchema.optional(), invocation_mode: z.enum(['direct', 'ask']).optional(), expected_policy_revision: z.number().int().nonnegative().optional()
}).strict().refine((tool) => Boolean(tool.activation_status || tool.invocation_mode), 'at least one change is required').refine((tool) => Boolean(tool.invocation_mode) === (tool.expected_policy_revision !== undefined), 'invocation_mode and expected_policy_revision must be provided together');
const openApiToolActivationBatchResponseItemSchema = z.object({
  tool_id: z.string().min(1), activation_status: openApiToolActivationStatusSchema, invocation_mode: z.enum(['direct', 'ask']), policy_revision: z.number().int().nonnegative()
}).strict();
export const openApiToolActivationBatchRequestSchema = z.object({
  tools: z.array(openApiToolActivationBatchRequestItemSchema).min(1)
}).strict().refine(({ tools }) => new Set(tools.map((tool) => tool.tool_id)).size === tools.length, 'tool_id values must be unique');
export const openApiToolActivationBatchResponseSchema = z.object({
  connector_id: z.string().min(1),
  tools: z.array(openApiToolActivationBatchResponseItemSchema)
}).strict();
export const openApiAuthenticationTypeSchema = z.enum(['none', 'bearer']);
export const openApiConfigurationRequestSchema = z.object({
  authentication_type: openApiAuthenticationTypeSchema,
  bearer_token: z.string()
}).strict();
export const openApiConfigurationResponseSchema = z.object({
  configured: z.boolean(),
  authentication_type: openApiAuthenticationTypeSchema,
  masked_token: z.literal('********').nullable()
}).strict();
export const openApiPublicationResponseSchema = z.object({
  connector_id: z.string().min(1),
  publication_status: openApiPublicationResultSchema
}).strict();

export type CreateOpenApiConnectorRequest = z.infer<typeof createOpenApiConnectorRequestSchema>;
export type OpenApiConfigurationRequest = z.infer<typeof openApiConfigurationRequestSchema>;
export type OpenApiConfiguration = z.infer<typeof openApiConfigurationResponseSchema>;
export type ImportOpenApiCatalogUrlRequest = z.infer<typeof importOpenApiCatalogUrlRequestSchema>;
export type ImportOpenApiCatalogDocumentRequest = z.infer<typeof importOpenApiCatalogDocumentRequestSchema>;
export type OpenApiConnector = z.infer<typeof openApiConnectorSchema>;
export type OpenApiConnectorSummary = z.infer<typeof openApiConnectorSummarySchema>;
export type OpenApiOperationTool = z.infer<typeof openApiOperationToolSchema>;
export type OpenApiToolActivationStatus = z.infer<typeof openApiToolActivationStatusSchema>;
export type OpenApiToolActivationBatchRequest = z.infer<typeof openApiToolActivationBatchRequestSchema>;
export type OpenApiToolActivationBatchResponse = z.infer<typeof openApiToolActivationBatchResponseSchema>;
export type OpenApiConnectorPublicationStatus = z.infer<typeof openApiConnectorPublicationStatusSchema>;
export type OpenApiAvailableAction = z.infer<typeof openApiAvailableActionSchema>;

export const openApiConnectorPublicationStatusLabels: Record<OpenApiConnectorPublicationStatus, string> = {
  unconfigured: 'Unconfigured',
  draft: 'Draft',
  published: 'Published',
  unpublished: 'Unpublished'
};

export type OpenApiConnectorListItem = {
  id: string;
  name: string;
  toolNamePrefix: string;
  capabilityDescription: string;
  publicationStatus: string;
  canPublish: boolean;
  canUnpublish: boolean;
  canImport: boolean;
  createdAt: string;
  updatedAt: string;
  tools: OpenApiOperationToolUiModel[];
};

export type OpenApiOperationToolUiModel = {
  operationId: string;
  method: string;
  path: string;
  summary: string;
  description: string;
  activationStatus: OpenApiToolActivationStatus;
  parameters?: ConnectorToolParameter[];
  outputSchema: ToolOutputSchemaState;
};

export type OpenApiConnectorDetailPageData =
  | {
      status: 'ready';
      connector: {
        id: string;
        name: string;
        toolNamePrefix: string;
        capabilityDescription: string;
        createdAt: string;
        updatedAt: string;
      };
      tools: OpenApiOperationToolUiModel[];
      publicationStatus: string;
      canPublish: boolean;
      canUnpublish: boolean;
    }
  | { status: 'missing'; message: string }
  | { status: 'failed'; message: string; retryLabel: string };

export type OpenApiConnectorCreateAction =
  | { status: 'invalid' | 'conflict' | 'failed'; displayName: string; message: string };

export type OpenApiConnectorListPageData =
  | { status: 'ready'; connectors: OpenApiConnectorListItem[] }
  | { status: 'empty'; message: string; connectors: [] }
  | { status: 'failed'; message: string; retryLabel: string; connectors: [] };

export function normalizeToolNamePrefix(value: string): string {
  return value.replace(/[^a-zA-Z0-9_-]+/g, '_').replace(/^_+|_+$/g, '') || 'connector';
}

export function mapOpenApiOperationTool(tool: OpenApiOperationTool): OpenApiOperationToolUiModel {
  return {
    operationId: tool.operation_id,
    method: tool.method,
    path: tool.path,
    summary: tool.summary,
    description: tool.description,
    activationStatus: tool.activation_status,
    parameters: mapJsonSchemaToConnectorToolParameters(tool.parameters),
    outputSchema: normalizeDeclaredToolOutputSchema(tool)
  };
}

export function mapOpenApiConnectorSummary(connector: OpenApiConnectorSummary): OpenApiConnectorListItem {
  return {
    id: connector.connector_id,
    name: connector.display_name,
    toolNamePrefix: '',
    capabilityDescription: '',
    publicationStatus: openApiConnectorPublicationStatusLabels[connector.publication_status],
    canPublish: connector.available_actions.includes('publish'),
    canUnpublish: connector.available_actions.includes('unpublish'),
    canImport: connector.available_actions.includes('import'),
    createdAt: '',
    updatedAt: '',
    tools: []
  };
}

export function mapOpenApiConnector(
  connector: OpenApiConnector,
  tools: OpenApiOperationToolUiModel[] = []
): OpenApiConnectorListItem {
  return {
    id: connector.connector_id,
    name: connector.display_name,
    toolNamePrefix: connector.tool_name_prefix,
    capabilityDescription: connector.capability_description,
    publicationStatus: openApiConnectorPublicationStatusLabels[connector.publication_status],
    canPublish: connector.available_actions.includes('publish'),
    canUnpublish: connector.available_actions.includes('unpublish'),
    canImport: connector.available_actions.includes('import'),
    createdAt: connector.created_at,
    updatedAt: connector.updated_at,
    tools
  };
}
