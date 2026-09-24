import { z } from 'zod';
import { normalizeDeclaredToolOutputSchema, type ToolOutputSchemaState } from './tool-output-schema';
import { nullishOptional } from './infrastructure/schema';
import { mapJsonSchemaToConnectorToolParameters } from './json-schema-tool-parameters';

export const connectorSourceSchema = z.enum(['built-in', 'user-supplied']);
export const connectorPublicationStatusSchema = z.enum(['unconfigured', 'draft', 'published', 'unpublished']);
export const connectorAvailableActionSchema = z.enum(['configure', 'publish', 'unpublish']);
export const connectorToolActivationStatusSchema = z.enum(['enabled', 'disabled']);

export type ConnectorSource = z.infer<typeof connectorSourceSchema>;
export type ConnectorPublicationStatus = z.infer<typeof connectorPublicationStatusSchema>;
export type ConnectorAvailableAction = z.infer<typeof connectorAvailableActionSchema>;
export type ConnectorToolActivationStatus = z.infer<typeof connectorToolActivationStatusSchema>;

export const connectorApiItemSchema = z.object({
  id: z.string(),
  display_name: z.string(),
  description: z.string(),
  icon_data_url: nullishOptional(z.string().startsWith('data:image/svg+xml;base64,')),
  extension: z.object({
    source: connectorSourceSchema
  }).strict(),
  publication_status: connectorPublicationStatusSchema,
  available_actions: z.array(connectorAvailableActionSchema)
}).strict();

export const connectorApiResponseSchema = z.object({
  connectors: z.array(connectorApiItemSchema)
}).strict();

export const connectorConfigurationApiFieldSchema = z.object({
  name: z.string(),
  type: z.string(),
  required: z.boolean(),
  secret: z.boolean()
});

export const connectorConfigurationApiResponseSchema = z.object({
  connector: z.object({
    id: z.string(),
    display_name: z.string()
  }),
  schema: z.object({
    fields: z.array(connectorConfigurationApiFieldSchema)
  }),
  configuration: z.record(z.string(), z.unknown()).nullable()
});

export const connectorToolParameterApiPropertySchema = z.object({
  type: nullishOptional(z.string()),
  description: nullishOptional(z.string())
}).strict();

export const connectorToolParametersApiSchema = z.object({
  type: z.string(),
  properties: nullishOptional(z.record(z.string(), connectorToolParameterApiPropertySchema)),
  required: nullishOptional(z.array(z.string()))
}).strict();

export const connectorToolOutputSchemaStateSchema = z.discriminatedUnion('output_schema_status', [
  z.object({
    output_schema_status: z.literal('absent'),
    output_schema: z.never().optional()
  }).strict(),
  z.object({
    output_schema_status: z.literal('present'),
    output_schema: z.record(z.string(), z.unknown())
  }).strict()
]);

export const connectorDetailApiResponseSchema = z.object({
  id: z.string(),
  display_name: z.string(),
  description: z.string(),
  capability_description: z.string().trim().min(1).max(300),
  base_capability_description: z.string().trim().min(1).max(300),
  effective_capability_description: z.string().trim().min(1).max(300),
  capability_description_override: z.object({
    state: z.enum(['system', 'overridden']),
    revision: z.number().int()
  }).strict(),
  icon_data_url: nullishOptional(z.string().startsWith('data:image/svg+xml;base64,')),
  extension: z.object({
    source: connectorSourceSchema,
    package: z.string().nullable()
  }).strict(),
  publication_status: connectorPublicationStatusSchema,
  tools: z.array(
    z.object({
      operation_name: z.string(),
      label: z.string(),
      description: z.string(),
      parameters: connectorToolParametersApiSchema,
      output_schema_status: z.literal('absent'),
      output_schema: z.never().optional()
    }).strict().or(z.object({
      operation_name: z.string(),
      label: z.string(),
      description: z.string(),
      parameters: connectorToolParametersApiSchema,
      output_schema_status: z.literal('present'),
      output_schema: z.record(z.string(), z.unknown())
    }).strict())
  )
}).strict();

const connectorToolActivationBatchRequestItemSchema = z.object({
  tool_id: z.string().min(1),
  activation_status: connectorToolActivationStatusSchema.optional(),
  invocation_mode: z.enum(['direct', 'ask']).optional(),
  expected_policy_revision: z.number().int().nonnegative().optional()
}).superRefine((tool, context) => {
  if (!tool.activation_status && !tool.invocation_mode) context.addIssue({ code: 'custom', message: 'At least one change is required' });
  if (tool.invocation_mode && tool.expected_policy_revision === undefined) context.addIssue({ code: 'custom', message: 'Expected policy revision is required', path: ['expected_policy_revision'] });
  if (!tool.invocation_mode && tool.expected_policy_revision !== undefined) context.addIssue({ code: 'custom', message: 'Invocation mode is required', path: ['invocation_mode'] });
});

const connectorToolActivationBatchResponseItemSchema = z.object({
  tool_id: z.string().min(1),
  activation_status: connectorToolActivationStatusSchema,
  invocation_mode: z.enum(['direct', 'ask']),
  policy_revision: z.number().int().nonnegative()
});

export const connectorToolActivationBatchRequestSchema = z.object({
  tools: z.array(connectorToolActivationBatchRequestItemSchema).min(1)
}).superRefine(({ tools }, context) => {
  const toolIds = new Set<string>();
  tools.forEach((tool, index) => {
    if (toolIds.has(tool.tool_id)) {
      context.addIssue({
        code: 'custom',
        message: 'tool_id values must be unique',
        path: ['tools', index, 'tool_id']
      });
    }
    toolIds.add(tool.tool_id);
  });
});

export const connectorToolActivationBatchResponseSchema = z.object({
  connector_id: z.string().min(1),
  tools: z.array(connectorToolActivationBatchResponseItemSchema)
});

export const connectorToolActivationApiResponseSchema = connectorToolActivationBatchResponseSchema;

export const saveConnectorConfigurationRequestSchema = z.object({
  configuration: z.record(z.string(), z.string())
});

export const connectorConfigurationCheckResultSchema = z.object({
  valid: z.boolean(),
  message: nullishOptional(z.string()),
  field_messages: nullishOptional(z.record(z.string(), z.string()))
});

export type ConnectorApiItem = z.infer<typeof connectorApiItemSchema>;
export type ConnectorApiResponse = z.infer<typeof connectorApiResponseSchema>;
export type ConnectorConfigurationApiField = z.infer<typeof connectorConfigurationApiFieldSchema>;
export type ConnectorConfigurationApiResponse = z.infer<typeof connectorConfigurationApiResponseSchema>;
export type ConnectorToolParameterApiProperty = z.infer<typeof connectorToolParameterApiPropertySchema>;
export type ConnectorToolParameterApiSchema = z.infer<typeof connectorToolParametersApiSchema>;
export type ConnectorDetailApiResponse = z.infer<typeof connectorDetailApiResponseSchema>;
export type ConnectorToolActivationBatchRequest = z.infer<typeof connectorToolActivationBatchRequestSchema>;
export type ConnectorToolActivationBatchResponse = z.infer<typeof connectorToolActivationBatchResponseSchema>;
export type ConnectorToolActivationApiResponse = z.infer<typeof connectorToolActivationApiResponseSchema>;
export type ConnectorToolOutputSchemaState = z.infer<typeof connectorToolOutputSchemaStateSchema>;
export type SaveConnectorConfigurationRequest = z.infer<typeof saveConnectorConfigurationRequestSchema>;
export type ConnectorConfigurationCheckResult = z.infer<typeof connectorConfigurationCheckResultSchema>;

export type ConnectorListItem = {
  id: string;
  name: string;
  description: string;
  iconDataUrl?: string;
  sourceLabel: string;
  configureHref: string;
  publicationStatus: string;
  isConfigured: boolean;
  canPublish: boolean;
  canUnpublish: boolean;
  tools: ConnectorTool[];
  configurationFields?: ConnectorConfigurationField[];
};

export type ConnectorListReadyPageData = {
  status: 'ready';
  successMessage: string | null;
  connectors: ConnectorListItem[];
};

export type ConnectorListEmptyPageData = {
  status: 'empty';
  message: string;
  connectors: ConnectorListItem[];
};

export type ConnectorListFailedPageData = {
  status: 'failed';
  message: string;
  retryLabel: string;
  connectors: ConnectorListItem[];
};

export type ConnectorListPageData =
  | ConnectorListReadyPageData
  | ConnectorListEmptyPageData
  | ConnectorListFailedPageData;

export type ConnectorConfigurationField = {
  name: string;
  label: string;
  inputType: 'text' | 'password';
  required: boolean;
  value: string;
  secretConfigured?: boolean;
  unsupported: boolean;
};

export type ConnectorConfigurationReadyPageData = {
  status: 'ready';
  connector: {
    id: string;
    name: string;
  };
  fields: ConnectorConfigurationField[];
  errorMessage: string | null;
};

export type ConnectorConfigurationFailedPageData = {
  status: 'failed';
  message: string;
  backHref: string;
};

export type ConnectorConfigurationPageData =
  | ConnectorConfigurationReadyPageData
  | ConnectorConfigurationFailedPageData;

export type ConnectorToolParameter = {
  name: string;
  label: string;
  type: string;
  description: string;
  required: boolean;
};

export type ConnectorTool = {
  operationName: string;
  label: string;
  description: string;
  parameters: ConnectorToolParameter[];
  outputSchema: ToolOutputSchemaState;
  activationStatus: ConnectorToolActivationStatus;
};

export type ConnectorDetailReadyPageData = {
  status: 'ready';
  connector: {
    id: string;
    name: string;
    description: string;
    iconDataUrl?: string;
    sourceLabel: string;
    publicationStatus: string;
  };
  tools: ConnectorTool[];
};

export type ConnectorDetailFailedPageData = {
  status: 'failed';
  message: string;
  backHref: string;
};

export type ConnectorDetailPageData = ConnectorDetailReadyPageData | ConnectorDetailFailedPageData;

export const connectorSourceLabels: Record<ConnectorSource, string> = {
  'built-in': 'Built-in',
  'user-supplied': 'User supplied'
};

export const connectorPublicationStatusLabels: Record<ConnectorPublicationStatus, string> = {
  unconfigured: 'Unconfigured',
  draft: 'Draft',
  published: 'Published',
  unpublished: 'Unpublished'
};

export function mapConnectorApiItem(connector: ConnectorApiItem): ConnectorListItem {
  const publicationStatus = connector.publication_status;
  const availableActions = connector.available_actions;
  return {
    id: connector.id,
    name: connector.display_name,
    description: connector.description,
    ...(connector.icon_data_url ? { iconDataUrl: connector.icon_data_url } : {}),
    sourceLabel: connectorSourceLabels[connector.extension.source],
    configureHref: `/admin/connectors/${connector.id}/configuration`,
    publicationStatus: connectorPublicationStatusLabels[publicationStatus],
    isConfigured: publicationStatus !== 'unconfigured',
    canPublish: availableActions.includes('publish'),
    canUnpublish: availableActions.includes('unpublish'),
    tools: []
  };
}

export function mapConnectorDetailApiResponse(
  response: ConnectorDetailApiResponse,
  activationResponse?: ConnectorToolActivationApiResponse
): ConnectorDetailReadyPageData {
  const activationStatusByOperationName = new Map(
    activationResponse?.tools.map((tool) => [tool.tool_id, tool.activation_status]) ?? []
  );
  return {
    status: 'ready',
    connector: {
      id: response.id,
      name: response.display_name,
      description: response.description,
      ...(response.icon_data_url ? { iconDataUrl: response.icon_data_url } : {}),
      sourceLabel: connectorSourceLabels[response.extension.source],
      publicationStatus: connectorPublicationStatusLabels[response.publication_status]
    },
    tools: response.tools.map((tool) => ({
      operationName: tool.operation_name,
      label: tool.label,
      description: tool.description,
      parameters: mapJsonSchemaToConnectorToolParameters(tool.parameters),
      outputSchema: normalizeDeclaredToolOutputSchema(tool),
      activationStatus: activationStatusByOperationName.get(tool.operation_name) ?? 'disabled'
    }))
  };
}

export function mapConnectorConfigurationApiResponse(
  response: ConnectorConfigurationApiResponse
): ConnectorConfigurationReadyPageData {
  return {
    status: 'ready',
    connector: {
      id: response.connector.id,
      name: response.connector.display_name
    },
    fields: response.schema.fields.map((field) => mapConnectorConfigurationField(field, response.configuration)),
    errorMessage: null
  };
}

export function formatConnectorConfigurationError(body: unknown): string {
  if (isValidationDetailBody(body)) {
    return body.detail.map((detail) => `${formatValidationLocation(detail.loc)}: ${detail.msg}`).join(', ');
  }

  if (isMessageBody(body)) {
    return body.message;
  }

  return 'Connector configuration could not be saved';
}

function mapConnectorConfigurationField(
  field: ConnectorConfigurationApiField,
  configuration: Record<string, unknown> | null
): ConnectorConfigurationField {
  const isSupported = field.type === 'string';
  const configuredValue = configuration?.[field.name];
  const fieldData: ConnectorConfigurationField = {
    name: field.name,
    label: formatFieldLabel(field.name),
    inputType: field.secret ? 'password' : 'text',
    required: field.required,
    value: field.secret ? '' : formatFieldValue(configuredValue),
    unsupported: !isSupported
  };

  if (field.secret) {
    fieldData.secretConfigured = typeof configuredValue === 'string' && configuredValue.length > 0;
  }

  return fieldData;
}

function formatFieldLabel(name: string): string {
  const label = name.replaceAll('_', ' ');
  return label.charAt(0).toUpperCase() + label.slice(1);
}

function formatFieldValue(value: unknown): string {
  return typeof value === 'string' ? value : '';
}

type ValidationDetail = {
  loc: unknown[];
  msg: string;
};

type ValidationDetailBody = {
  detail: ValidationDetail[];
};

type MessageBody = {
  message: string;
};

function isValidationDetailBody(body: unknown): body is ValidationDetailBody {
  return (
    typeof body === 'object' &&
    body !== null &&
    'detail' in body &&
    Array.isArray(body.detail) &&
    body.detail.every(
      (detail) =>
        typeof detail === 'object' &&
        detail !== null &&
        'loc' in detail &&
        Array.isArray(detail.loc) &&
        'msg' in detail &&
        typeof detail.msg === 'string'
    )
  );
}

function isMessageBody(body: unknown): body is MessageBody {
  return typeof body === 'object' && body !== null && 'message' in body && typeof body.message === 'string';
}

function formatValidationLocation(location: unknown[]): string {
  const fieldLocation = location.filter((part) => typeof part === 'string').at(-1);
  return fieldLocation ?? 'configuration';
}
