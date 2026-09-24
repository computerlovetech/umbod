import { HttpError, isOperationalError, type Transport } from './infrastructure/transport';
import {
  connectorApiResponseSchema,
  connectorConfigurationApiResponseSchema,
  connectorConfigurationCheckResultSchema,
  connectorDetailApiResponseSchema,
  connectorToolActivationApiResponseSchema,
  connectorToolActivationBatchRequestSchema,
  connectorToolActivationBatchResponseSchema,
  formatConnectorConfigurationError,
  mapConnectorApiItem,
  mapConnectorConfigurationApiResponse,
  saveConnectorConfigurationRequestSchema,
  type ConnectorConfigurationFailedPageData,
  type ConnectorConfigurationPageData,
  type ConnectorListFailedPageData,
  type ConnectorListItem,
  type ConnectorListPageData,
  type SaveConnectorConfigurationRequest
} from './connectors';
import type { ToolActivationSaveInput } from './connectors-forms';
import { promptCatalogSchema, promptActivationBatchRequestSchema, promptActivationBatchResponseSchema, resourceCatalogWireSchema, resourceActivationBatchRequestSchema, resourceActivationBatchResponseSchema, type PromptActivationBatchRequest, type ResourceActivationBatchRequest } from './capability-catalogs';
import type { ToolActivationCapability, ToolActivationChange } from './tool-activation-capability';

export type PublicationActionResult =
  | { status: 'published'; successMessage: string }
  | { status: 'unpublished'; successMessage: string }
  | { status: 'failed'; errorMessage: string };

export type SaveToolActivationsResult = {
  status: 'saved' | 'failed';
  connectorId: string;
};

export type SaveConnectorConfigurationResult = { status: 'saved' } | { status: 'failed'; errorMessage: string };

export type CheckConnectorConfigurationResult =
  | { status: 'valid' }
  | { status: 'invalid'; message: string; fieldMessages: Record<string, string> }
  | { status: 'failed'; errorMessage: string };

function connectorPath(connectorId: string): string {
  return `/admin/connectors/catalog/${encodeURIComponent(connectorId)}`;
}

function activationCollectionPath(connectorId: string): string {
  return `${connectorPath(connectorId)}/tools/activation`;
}

class ConnectorsRoute {
  constructor(private readonly transport: Transport) {}

  list() {
    return this.transport.request({ method: 'GET', path: '/admin/connectors/catalog', outputSchema: connectorApiResponseSchema });
  }

  get(connectorId: string) {
    return this.transport.request({ method: 'GET', path: connectorPath(connectorId), outputSchema: connectorDetailApiResponseSchema });
  }

  getConfiguration(connectorId: string) {
    return this.transport.request({
      method: 'GET',
      path: `${connectorPath(connectorId)}/configuration`,
      outputSchema: connectorConfigurationApiResponseSchema
    });
  }

  saveConfiguration(connectorId: string, body: SaveConnectorConfigurationRequest): Promise<void> {
    return this.transport.request({
      method: 'PUT',
      path: `${connectorPath(connectorId)}/configuration`,
      body,
      inputSchema: saveConnectorConfigurationRequestSchema
    });
  }

  checkConfiguration(connectorId: string, body: SaveConnectorConfigurationRequest) {
    return this.transport.request({
      method: 'POST',
      path: `${connectorPath(connectorId)}/configuration/validations`,
      body,
      inputSchema: saveConnectorConfigurationRequestSchema,
      outputSchema: connectorConfigurationCheckResultSchema
    });
  }

  publish(connectorId: string): Promise<void> {
    return this.transport.request({ method: 'PUT', path: `${connectorPath(connectorId)}/publication` });
  }

  unpublish(connectorId: string): Promise<void> {
    return this.transport.request({ method: 'DELETE', path: `${connectorPath(connectorId)}/publication` });
  }
}

class ConnectorPromptsRoute {
  constructor(private readonly transport: Transport) {}

  list(connectorId: string) {
    return this.transport.request({ method: 'GET', path: `${connectorPath(connectorId)}/prompts`, outputSchema: promptCatalogSchema });
  }

  saveActivations(connectorId: string, body: PromptActivationBatchRequest) {
    return this.transport.request({
      method: 'PUT',
      path: `${connectorPath(connectorId)}/prompts/activation`,
      body,
      inputSchema: promptActivationBatchRequestSchema,
      outputSchema: promptActivationBatchResponseSchema
    });
  }
}

class ConnectorResourcesRoute {
  constructor(private readonly transport: Transport) {}

  list(connectorId: string) {
    return this.transport.request({ method: 'GET', path: `${connectorPath(connectorId)}/resources`, outputSchema: resourceCatalogWireSchema });
  }

  saveActivations(connectorId: string, body: ResourceActivationBatchRequest) {
    return this.transport.request({
      method: 'PUT',
      path: `${connectorPath(connectorId)}/resources/activation`,
      body,
      inputSchema: resourceActivationBatchRequestSchema,
      outputSchema: resourceActivationBatchResponseSchema
    });
  }
}

class ConnectorToolsRoute implements ToolActivationCapability {
  constructor(private readonly transport: Transport) {}

  listActivations(connectorId: string) {
    return this.transport.request({
      method: 'GET',
      path: `${connectorPath(connectorId)}/tools`,
      outputSchema: connectorToolActivationApiResponseSchema
    });
  }

  saveActivations(connectorId: string, changes: ToolActivationChange[]) {
    return this.transport.request({
      method: 'PUT',
      path: activationCollectionPath(connectorId),
      body: {
        tools: changes.map((change) => ({
          tool_id: change.toolId,
          activation_status: change.activationStatus,
          invocation_mode: change.invocationMode,
          expected_policy_revision: change.expectedPolicyRevision
        }))
      },
      inputSchema: connectorToolActivationBatchRequestSchema,
      outputSchema: connectorToolActivationBatchResponseSchema
    });
  }
}

export class ConnectorsApi {
  readonly connectors: ConnectorsRoute;
  readonly tools: ConnectorToolsRoute;
  readonly prompts: ConnectorPromptsRoute;
  readonly resources: ConnectorResourcesRoute;

  constructor(transport: Transport) {
    this.connectors = new ConnectorsRoute(transport);
    this.prompts = new ConnectorPromptsRoute(transport);
    this.resources = new ConnectorResourcesRoute(transport);
    this.tools = new ConnectorToolsRoute(transport);
  }
}

const configurationLoadFailure: ConnectorConfigurationFailedPageData = {
  status: 'failed',
  message: 'Connector configuration could not be loaded',
  backHref: '/admin/connectors'
};

export async function loadConnectorList(api: ConnectorsApi, configuredConnectorId: string | null): Promise<ConnectorListPageData> {
  try {
    const apiResponse = await api.connectors.list();
    const connectors = apiResponse.connectors.map(mapConnectorApiItem);

    if (connectors.length === 0) {
      return { status: 'empty', message: 'No connectors are currently available', connectors: [] };
    }

    return createReadyPageData(connectors, configuredConnectorId);
  } catch (error) {
    if (!isOperationalError(error)) throw error;
    return createFailurePageData();
  }
}

export async function loadConnectorConfiguration(api: ConnectorsApi, connectorId: string): Promise<ConnectorConfigurationPageData> {
  try {
    const apiResponse = await api.connectors.getConfiguration(connectorId);
    return mapConnectorConfigurationApiResponse(apiResponse);
  } catch (error) {
    if (!isOperationalError(error)) throw error;
    return configurationLoadFailure;
  }
}

export async function publishConnector(api: ConnectorsApi, connectorId: string): Promise<PublicationActionResult> {
  try {
    await api.connectors.publish(connectorId);
    return { status: 'published', successMessage: `${connectorName(connectorId)} was published successfully` };
  } catch (error) {
    if (!isOperationalError(error)) throw error;
    return { status: 'failed', errorMessage: publicationErrorMessage(error) };
  }
}

export async function unpublishConnector(api: ConnectorsApi, connectorId: string): Promise<PublicationActionResult> {
  try {
    await api.connectors.unpublish(connectorId);
    return { status: 'unpublished', successMessage: `${connectorName(connectorId)} was unpublished successfully` };
  } catch (error) {
    if (!isOperationalError(error)) throw error;
    return { status: 'failed', errorMessage: publicationErrorMessage(error) };
  }
}

export async function saveToolActivations(api: ConnectorsApi, input: ToolActivationSaveInput): Promise<SaveToolActivationsResult> {
  try {
    await api.tools.saveActivations(input.connectorId, input.activations.map((activation) => ({
      toolId: activation.operationName,
      activationStatus: activation.activationStatus
    })));
    return { status: 'saved', connectorId: input.connectorId };
  } catch (error) {
    if (!isOperationalError(error)) throw error;
    return { status: 'failed', connectorId: input.connectorId };
  }
}

export async function saveConnectorConfiguration(
  api: ConnectorsApi,
  connectorId: string,
  configuration: Record<string, string>
): Promise<SaveConnectorConfigurationResult> {
  try {
    await api.connectors.saveConfiguration(connectorId, { configuration });
    return { status: 'saved' };
  } catch (error) {
    if (error instanceof HttpError) {
      return { status: 'failed', errorMessage: formatConnectorConfigurationError(error.body) };
    }
    if (!isOperationalError(error)) throw error;
    return { status: 'failed', errorMessage: 'Connector configuration could not be saved' };
  }
}

export async function checkConnectorConfiguration(
  api: ConnectorsApi,
  connectorId: string,
  configuration: Record<string, string>
): Promise<CheckConnectorConfigurationResult> {
  try {
    const result = await api.connectors.checkConfiguration(connectorId, { configuration });
    if (result.valid) {
      return { status: 'valid' };
    }
    return {
      status: 'invalid',
      message: result.message ?? 'Connector configuration check failed',
      fieldMessages: result.field_messages ?? {}
    };
  } catch (error) {
    if (error instanceof HttpError) {
      return { status: 'failed', errorMessage: formatConnectorConfigurationError(error.body) };
    }
    if (!isOperationalError(error)) throw error;
    return { status: 'failed', errorMessage: 'Connector configuration could not be checked' };
  }
}

function createReadyPageData(connectors: ConnectorListItem[], configuredConnectorId: string | null): ConnectorListPageData {
  const configuredConnector = connectors.find((connector) => connector.id === configuredConnectorId);

  return {
    status: 'ready',
    successMessage: configuredConnector ? `${configuredConnector.name} was configured successfully` : null,
    connectors
  };
}

function createFailurePageData(): ConnectorListFailedPageData {
  return {
    status: 'failed',
    message: 'Failed to get connectors',
    retryLabel: 'Try again',
    connectors: []
  };
}

function connectorName(connectorId: string): string {
  return connectorId;
}

function publicationErrorMessage(error: unknown): string {
  if (error instanceof HttpError && isMessageBody(error.body)) {
    return error.body.message;
  }
  return 'Connector could not be published';
}

function isMessageBody(body: unknown): body is { message: string } {
  return typeof body === 'object' && body !== null && 'message' in body && typeof body.message === 'string';
}
