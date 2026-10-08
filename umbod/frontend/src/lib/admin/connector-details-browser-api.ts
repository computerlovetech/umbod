import { AdminApi } from './infrastructure/admin-api';
import { browserTransport } from './infrastructure/transport';
import { browserRequest } from './infrastructure/browser-request';
import { mapResourceCatalog, type PromptCatalog, type ResourceCatalog } from './capability-catalogs';
import type { InvocationPolicyTool } from './invocation-policy';
import { mapConnectorConfigurationApiResponse, mapConnectorDetailApiResponse, type ConnectorConfigurationField, type ConnectorDetailReadyPageData } from './connectors';

export type ConnectorDetailBundle = {
  detail: ConnectorDetailReadyPageData;
  configurationFields: ConnectorConfigurationField[];
  promptCatalog: PromptCatalog;
  resourceCatalog: ResourceCatalog;
  invocationPolicies?: InvocationPolicyTool[];
};

export class ConnectorDetailsBrowserRoute {
  constructor(private readonly request: typeof fetch = globalThis.fetch) {}
  async get(connectorId: string, signal?: AbortSignal): Promise<ConnectorDetailBundle> {
    const transport = browserTransport({ fetch: this.request });
    const api = new AdminApi({ request: (options) => transport.request({ ...options, signal }) }).connectors;
    return browserRequest(async () => {
      const [connector, activation, configuration, prompts, resources] = await Promise.all([
        api.connectors.get(connectorId), api.tools.listActivations(connectorId), api.connectors.getConfiguration(connectorId), api.prompts.list(connectorId), api.resources.list(connectorId)
      ]);
      return {
        detail: mapConnectorDetailApiResponse(connector, activation),
        configurationFields: mapConnectorConfigurationApiResponse(configuration).fields,
        promptCatalog: prompts,
        resourceCatalog: mapResourceCatalog(resources),
        invocationPolicies: activation.tools.map((tool) => ({ tool_id: tool.tool_id, mode: tool.invocation_mode, revision: tool.policy_revision }))
      };
    });
  }
}
