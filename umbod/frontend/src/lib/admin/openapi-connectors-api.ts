import { HttpError, isOperationalError, type Transport } from './infrastructure/transport';
import {
  createOpenApiConnectorRequestSchema, importOpenApiCatalogDocumentRequestSchema, importOpenApiCatalogFileMetadataSchema,
  mapOpenApiConnector, mapOpenApiConnectorSummary, mapOpenApiOperationTool, openApiCatalogImportResponseSchema, openApiConnectorListResponseSchema, openApiGrantConflictResponseSchema,
  openApiConnectorSchema, openApiConfigurationRequestSchema, openApiConfigurationResponseSchema, openApiOperationToolListResponseSchema, openApiPublicationResponseSchema,
  openApiToolActivationBatchRequestSchema, openApiToolActivationBatchResponseSchema, type CreateOpenApiConnectorRequest, type ImportOpenApiCatalogDocumentRequest, type OpenApiConnectorCreateAction,
  type OpenApiConfigurationRequest, type OpenApiConnectorDetailPageData, type OpenApiConnectorListItem, type OpenApiConnectorListPageData
} from './openapi-connectors';
import type { ToolActivationCapability, ToolActivationChange } from './tool-activation-capability';

export interface OpenApiConnectorPort extends ToolActivationCapability {
  list(): ReturnType<OpenApiConnectorsRoute['list']>;
  create(input: CreateOpenApiConnectorRequest): ReturnType<OpenApiConnectorsRoute['create']>;
  get(connectorId: string): ReturnType<OpenApiConnectorsRoute['get']>;
  delete(connectorId: string): ReturnType<OpenApiConnectorsRoute['delete']>;
  listTools(connectorId: string): ReturnType<OpenApiConnectorsRoute['listTools']>;
  listActivations(connectorId: string): ReturnType<OpenApiConnectorsRoute['listActivations']>;
  saveActivations(connectorId: string, changes: ToolActivationChange[]): ReturnType<OpenApiConnectorsRoute['saveActivations']>;
  getConfiguration(connectorId: string): ReturnType<OpenApiConnectorsRoute['getConfiguration']>;
  putConfiguration(connectorId: string, input: OpenApiConfigurationRequest): ReturnType<OpenApiConnectorsRoute['putConfiguration']>;
  publish(connectorId: string): ReturnType<OpenApiConnectorsRoute['publish']>;
  unpublish(connectorId: string): ReturnType<OpenApiConnectorsRoute['unpublish']>;
}

export class OpenApiConnectorsRoute implements OpenApiConnectorPort {
  constructor(private readonly transport: Transport) {}
  list() { return this.transport.request({ method: 'GET', path: '/admin/connectors/openapi', outputSchema: openApiConnectorListResponseSchema }); }
  create(body: CreateOpenApiConnectorRequest) { return this.transport.request({ method: 'POST', path: '/admin/connectors/openapi', body, inputSchema: createOpenApiConnectorRequestSchema, outputSchema: openApiConnectorSchema }); }
  get(connectorId: string) { return this.transport.request({ method: 'GET', path: `/admin/connectors/openapi/${encodeURIComponent(connectorId)}`, outputSchema: openApiConnectorSchema }); }
  delete(connectorId: string) { return this.transport.request({ method: 'DELETE', path: `/admin/connectors/openapi/${encodeURIComponent(connectorId)}` }); }
  listTools(connectorId: string) { return this.transport.request({ method: 'GET', path: `/admin/connectors/openapi/${encodeURIComponent(connectorId)}/tools`, outputSchema: openApiOperationToolListResponseSchema }); }
  listActivations(connectorId: string) {
    return this.transport.request({ method: 'GET', path: `/admin/connectors/openapi/${encodeURIComponent(connectorId)}/tools/activation`, outputSchema: openApiToolActivationBatchResponseSchema });
  }
  saveActivations(connectorId: string, changes: ToolActivationChange[]) {
    const body = {
      tools: changes.map((change) => ({
        tool_id: change.toolId,
        activation_status: change.activationStatus,
        invocation_mode: change.invocationMode,
        expected_policy_revision: change.expectedPolicyRevision
      }))
    };
    return this.transport.request({
      method: 'PUT',
      path: `/admin/connectors/openapi/${encodeURIComponent(connectorId)}/tools/activation`,
      body,
      inputSchema: openApiToolActivationBatchRequestSchema,
      outputSchema: openApiToolActivationBatchResponseSchema
    });
  }
  getConfiguration(connectorId: string) {
    return this.transport.request({ method: 'GET', path: `/admin/connectors/openapi/${encodeURIComponent(connectorId)}/configuration`, outputSchema: openApiConfigurationResponseSchema });
  }
  putConfiguration(connectorId: string, body: OpenApiConfigurationRequest) {
    return this.transport.request({ method: 'PUT', path: `/admin/connectors/openapi/${encodeURIComponent(connectorId)}/configuration`, body, inputSchema: openApiConfigurationRequestSchema, outputSchema: openApiConfigurationResponseSchema });
  }
  publish(connectorId: string) {
    return this.transport.request({
      method: 'PUT',
      path: `/admin/connectors/openapi/${encodeURIComponent(connectorId)}/publication`,
      outputSchema: openApiPublicationResponseSchema
    });
  }
  unpublish(connectorId: string) {
    return this.transport.request({
      method: 'DELETE',
      path: `/admin/connectors/openapi/${encodeURIComponent(connectorId)}/publication`,
      outputSchema: openApiPublicationResponseSchema
    });
  }
}

export class InMemoryOpenApiConnectorApi implements OpenApiConnectorPort {
  private configurationConfigured = false;
  private readonly activationStatuses = new Map<string, 'enabled' | 'disabled'>();
  private readonly invocationPolicies = new Map<string, { mode: 'direct' | 'ask'; revision: number }>();

  constructor(private readonly connector: unknown, private readonly toolsResponse: unknown = { tools: [] }) {}
  async list() {
    const detail = openApiConnectorSchema.parse(this.connector);
    return openApiConnectorListResponseSchema.parse({
      connectors: [{
        connector_id: detail.connector_id,
        display_name: detail.display_name,
        publication_status: detail.publication_status,
        available_actions: detail.available_actions
      }]
    });
  }
  async create(input: CreateOpenApiConnectorRequest) { createOpenApiConnectorRequestSchema.parse(input); return openApiConnectorSchema.parse(this.connector); }
  async delete(_connectorId: string) {}
  async get(_connectorId: string) { return openApiConnectorSchema.parse(this.connector); }
  async listTools(connectorId: string) {
    const response = openApiOperationToolListResponseSchema.parse(this.toolsResponse);
    return openApiOperationToolListResponseSchema.parse({
      tools: response.tools.map((tool) => ({ ...tool, activation_status: this.activationStatus(connectorId, tool.operation_id, tool.activation_status) }))
    });
  }
  async listActivations(connectorId: string) {
    this.validateConnectorIdentity(connectorId);
    const response = openApiOperationToolListResponseSchema.parse(this.toolsResponse);
    return openApiToolActivationBatchResponseSchema.parse({
      connector_id: connectorId,
      tools: response.tools.map((tool) => {
        const policy = this.policy(connectorId, tool.operation_id);
        return { tool_id: tool.operation_id, activation_status: this.activationStatus(connectorId, tool.operation_id, tool.activation_status), invocation_mode: policy.mode, policy_revision: policy.revision };
      })
    });
  }
  async saveActivations(connectorId: string, changes: ToolActivationChange[]) {
    this.validateConnectorIdentity(connectorId);
    const request = openApiToolActivationBatchRequestSchema.parse({
      tools: changes.map((change) => ({ tool_id: change.toolId, activation_status: change.activationStatus, invocation_mode: change.invocationMode, expected_policy_revision: change.expectedPolicyRevision }))
    });
    const existingTools = openApiOperationToolListResponseSchema.parse(this.toolsResponse).tools;
    const knownToolIds = new Set(existingTools.map((tool) => tool.operation_id));
    if (request.tools.some((tool) => !knownToolIds.has(tool.tool_id))) {
      throw new HttpError(404, 'Not Found', { detail: 'Connector tool was not found' });
    }
    const conflicts = request.tools.flatMap((tool) => {
      if (tool.invocation_mode === undefined) return [];
      const current = this.policy(connectorId, tool.tool_id);
      return tool.expected_policy_revision === current.revision ? [] : [{ tool_id: tool.tool_id, expected_revision: tool.expected_policy_revision, current_mode: current.mode, current_revision: current.revision }];
    });
    if (conflicts.length > 0) throw new HttpError(409, 'Conflict', { code: 'invocation_policy_revision_conflict', conflicts });
    const results = request.tools.map((tool) => {
      const existing = existingTools.find((candidate) => candidate.operation_id === tool.tool_id);
      const currentPolicy = this.policy(connectorId, tool.tool_id);
      const nextPolicy = tool.invocation_mode !== undefined && tool.invocation_mode !== currentPolicy.mode
        ? { mode: tool.invocation_mode, revision: currentPolicy.revision + 1 }
        : currentPolicy;
      const activationStatus = tool.activation_status ?? this.activationStatus(connectorId, tool.tool_id, existing?.activation_status ?? 'disabled');
      if (tool.activation_status !== undefined) this.activationStatuses.set(this.toolKey(connectorId, tool.tool_id), tool.activation_status);
      if (tool.invocation_mode !== undefined) this.invocationPolicies.set(this.toolKey(connectorId, tool.tool_id), nextPolicy);
      return { tool_id: tool.tool_id, activation_status: activationStatus, invocation_mode: nextPolicy.mode, policy_revision: nextPolicy.revision };
    });
    return openApiToolActivationBatchResponseSchema.parse({ connector_id: connectorId, tools: results });
  }
  private validateConnectorIdentity(connectorId: string): void {
    if (connectorId !== openApiConnectorSchema.parse(this.connector).connector_id) {
      throw new HttpError(404, 'Not Found', { detail: 'OpenAPI connector not found' });
    }
  }
  private toolKey(connectorId: string, toolId: string): string { return `${connectorId}\u0000${toolId}`; }
  private policy(connectorId: string, toolId: string): { mode: 'direct' | 'ask'; revision: number } { return this.invocationPolicies.get(this.toolKey(connectorId, toolId)) ?? { mode: 'direct', revision: 0 }; }
  private activationStatus(connectorId: string, toolId: string, initial: 'enabled' | 'disabled'): 'enabled' | 'disabled' { return this.activationStatuses.get(this.toolKey(connectorId, toolId)) ?? initial; }
  async getConfiguration(_connectorId: string) { return openApiConfigurationResponseSchema.parse({ configured: this.configurationConfigured, authentication_type: this.configurationConfigured ? 'bearer' : 'none', masked_token: this.configurationConfigured ? '********' : null }); }
  async putConfiguration(_connectorId: string, input: OpenApiConfigurationRequest) {
    const parsed = openApiConfigurationRequestSchema.parse(input);
    if (parsed.authentication_type === 'none') this.configurationConfigured = false;
    else if (parsed.bearer_token.trim()) this.configurationConfigured = true;
    return this.getConfiguration(_connectorId);
  }
  async publish(connectorId: string) {
    return openApiPublicationResponseSchema.parse({ connector_id: connectorId, publication_status: 'published' });
  }
  async unpublish(connectorId: string) {
    return openApiPublicationResponseSchema.parse({ connector_id: connectorId, publication_status: 'unpublished' });
  }
}

export class OpenApiCatalogImportRoute {
  constructor(private readonly transport: Transport) {}
  importMultipart(connectorId: string, form: FormData, approvedHosts: string[]) {
    return this.transport.request({
      method: 'POST', path: `/admin/connectors/openapi/${encodeURIComponent(connectorId)}/imports`, outputSchema: openApiCatalogImportResponseSchema,
      requestBody: { kind: 'multipart', form, metadata: { approved_hosts: approvedHosts }, metadataSchema: importOpenApiCatalogFileMetadataSchema }
    });
  }
  importJson(connectorId: string, value: ImportOpenApiCatalogDocumentRequest) {
    return this.transport.request({
      method: 'POST', path: `/admin/connectors/openapi/${encodeURIComponent(connectorId)}/imports`, outputSchema: openApiCatalogImportResponseSchema,
      requestBody: { kind: 'json', value, schema: importOpenApiCatalogDocumentRequestSchema }
    });
  }
}

export class OpenApiConnectorsApi {
  readonly connectors: OpenApiConnectorsRoute;
  readonly imports: OpenApiCatalogImportRoute;
  constructor(transport: Transport) {
    this.connectors = new OpenApiConnectorsRoute(transport);
    this.imports = new OpenApiCatalogImportRoute(transport);
  }
}

export async function loadOpenApiConnectorList(api: { connectors: Pick<OpenApiConnectorPort, 'list'> }): Promise<OpenApiConnectorListPageData> {
  try {
    const response = await api.connectors.list();
    if (response.connectors.length === 0) return { status: 'empty', message: 'No OpenAPI connectors are currently available', connectors: [] };
    return { status: 'ready', connectors: response.connectors.map(mapOpenApiConnectorSummary) };
  } catch (error) {
    if (!isOperationalError(error)) throw error;
    return { status: 'failed', message: 'OpenAPI connectors are unavailable', retryLabel: 'Try again', connectors: [] };
  }
}

export async function loadOpenApiConnectorDetail(api: { connectors: Pick<OpenApiConnectorPort, 'get' | 'listTools'> }, connectorId: string): Promise<OpenApiConnectorDetailPageData> {
  try {
    const [connector, toolsResponse] = await Promise.all([api.connectors.get(connectorId), api.connectors.listTools(connectorId)]);
    const mapped = mapOpenApiConnector(connector);
    return {
      status: 'ready',
      connector: { id: mapped.id, name: mapped.name, toolNamePrefix: mapped.toolNamePrefix, capabilityDescription: mapped.capabilityDescription, createdAt: connector.created_at, updatedAt: connector.updated_at },
      tools: toolsResponse.tools.map(mapOpenApiOperationTool),
      publicationStatus: mapped.publicationStatus,
      canPublish: mapped.canPublish,
      canUnpublish: mapped.canUnpublish
    };
  } catch (error) {
    if (error instanceof HttpError && error.status === 404) return { status: 'missing', message: 'This OpenAPI connector could not be found. It may have changed or been removed.' };
    if (!isOperationalError(error)) throw error;
    return { status: 'failed', message: 'OpenAPI connector details are unavailable. Try again.', retryLabel: 'Try again' };
  }
}
export async function setOpenApiPublication(
  api: { connectors: Pick<OpenApiConnectorPort, 'publish' | 'unpublish'> },
  connectorId: string,
  publicationStatus: 'published' | 'unpublished'
) {
  try {
    const result = publicationStatus === 'published'
      ? await api.connectors.publish(connectorId)
      : await api.connectors.unpublish(connectorId);
    return { status: 'saved' as const, publicationStatus: result.publication_status === 'published' ? 'Published' as const : 'Unpublished' as const };
  } catch (error) {
    if (error instanceof HttpError && error.status === 404) return { status: 'stale' as const, message: 'This connector no longer exists. Reload before trying again.' };
    if (!isOperationalError(error)) throw error;
    return { status: 'failed' as const, message: 'Publication change is unavailable. Try again.' };
  }
}

export type OpenApiImportConflictResult = { status: 'conflict'; removedOperationIds: string[]; affectedGroupIds: string[] };

export function openApiImportConflictResult(error: unknown): OpenApiImportConflictResult | null {
  if (!(error instanceof HttpError) || error.status !== 409) return null;
  const conflict = openApiGrantConflictResponseSchema.safeParse(error.body);
  if (!conflict.success) return null;
  return { status: 'conflict', removedOperationIds: conflict.data.detail.removed_operation_ids, affectedGroupIds: conflict.data.detail.affected_group_ids };
}

export async function createOpenApiConnector(api: { connectors: Pick<OpenApiConnectorPort, 'create'> }, displayName: string, toolNamePrefix: string, capabilityDescription: string): Promise<{ connectorId: string } | OpenApiConnectorCreateAction> {
  const trimmed = displayName.trim();
  const trimmedToolNamePrefix = toolNamePrefix.trim();
  const trimmedCapabilityDescription = capabilityDescription.trim();
  if (!trimmed) return { status: 'invalid', displayName, message: 'Enter a display name' };
  if (!/^[a-zA-Z0-9_-]+$/.test(trimmedToolNamePrefix)) return { status: 'invalid', displayName, message: 'Enter a tool name prefix using letters, numbers, underscores, or hyphens' };
  if (!trimmedCapabilityDescription || trimmedCapabilityDescription.length > 300) return { status: 'invalid', displayName, message: 'Enter a capability description of at most 300 characters' };
  try { const connector = await api.connectors.create({ display_name: trimmed, tool_name_prefix: trimmedToolNamePrefix, capability_description: trimmedCapabilityDescription }); return { connectorId: connector.connector_id }; }
  catch (error) {
    if (error instanceof HttpError && (error.status === 409 || error.status === 422)) return { status: 'conflict', displayName, message: 'A connector with this display name already exists or is invalid.' };
    if (!isOperationalError(error)) throw error;
    return { status: 'failed', displayName, message: 'OpenAPI connector creation is unavailable. Try again.' };
  }
}
