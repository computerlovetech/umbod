import { AdminApi } from './infrastructure/admin-api';
import { browserTransport } from './infrastructure/transport';
import { browserRequest } from './infrastructure/browser-request';
import type { InvocationPolicyTool } from './invocation-policy';
import { mapOpenApiConnector, type OpenApiConnectorListItem } from './openapi-connectors';

export type OpenApiConnectorDetailBundle = { connector: OpenApiConnectorListItem; invocationPolicies: InvocationPolicyTool[] };

export class OpenApiConnectorDetailsBrowserRoute {
  constructor(private readonly request: typeof fetch = globalThis.fetch) {}
  async get(connectorId: string, signal?: AbortSignal): Promise<OpenApiConnectorDetailBundle> {
    const transport = browserTransport({ fetch: this.request });
    const api = new AdminApi({ request: (options) => transport.request({ ...options, signal }) }).openApiConnectors;
    return browserRequest(async () => {
      const [connector, activation] = await Promise.all([api.connectors.get(connectorId), api.connectors.listActivations(connectorId)]);
      return { connector: mapOpenApiConnector(connector), invocationPolicies: activation.tools.map((tool) => ({ tool_id: tool.tool_id, mode: tool.invocation_mode, revision: tool.policy_revision })) };
    });
  }
}
