import { z } from 'zod';
import { BrowserRequestError, fetchResponse } from './infrastructure/browser-request';
import { mapResourceCatalog, promptCatalogSchema, resourceCatalogWireSchema, type PromptCatalog, type ResourceCatalog } from './capability-catalogs';
import { invocationPolicyListResponseSchema, type InvocationPolicyTool } from './invocation-policy';
import {
  connectorConfigurationApiResponseSchema,
  connectorDetailApiResponseSchema,
  connectorToolActivationApiResponseSchema,
  mapConnectorConfigurationApiResponse,
  mapConnectorDetailApiResponse,
  type ConnectorConfigurationField,
  type ConnectorDetailReadyPageData
} from './connectors';

const connectorDetailBundleSchema = z.object({
  connector: connectorDetailApiResponseSchema,
  activation: connectorToolActivationApiResponseSchema,
  configuration: connectorConfigurationApiResponseSchema,
  prompts: promptCatalogSchema,
  resources: resourceCatalogWireSchema,
  invocationPolicies: invocationPolicyListResponseSchema
});

export type ConnectorDetailBundle = {
  detail: ConnectorDetailReadyPageData;
  configurationFields: ConnectorConfigurationField[];
  promptCatalog: PromptCatalog;
  resourceCatalog: ResourceCatalog;
  invocationPolicies?: InvocationPolicyTool[];
};

export class ConnectorDetailsBrowserRoute {
  constructor(private readonly request: typeof globalThis.fetch = globalThis.fetch) {}

  async get(connectorId: string, signal?: AbortSignal): Promise<ConnectorDetailBundle> {
    const response = await fetchResponse(this.request, `/admin/connectors/data/connectors/${encodeURIComponent(connectorId)}`, { signal });
    if (!response.ok) throw new BrowserRequestError(response.status);
    const payload = connectorDetailBundleSchema.parse(await response.json());
    return {
      detail: mapConnectorDetailApiResponse(payload.connector, payload.activation),
      configurationFields: mapConnectorConfigurationApiResponse(payload.configuration).fields,
      promptCatalog: payload.prompts,
      resourceCatalog: mapResourceCatalog(payload.resources),
      invocationPolicies: payload.invocationPolicies.tools
    };
  }
}
