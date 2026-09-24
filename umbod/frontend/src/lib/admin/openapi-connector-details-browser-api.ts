import { BrowserRequestError, fetchResponse } from './infrastructure/browser-request';
import { z } from 'zod';
import { invocationPolicyListResponseSchema, type InvocationPolicyTool } from './invocation-policy';
import { mapOpenApiConnector, openApiConnectorSchema, type OpenApiConnectorListItem } from './openapi-connectors';

const openApiConnectorDetailBundleSchema = z.object({
  connector: openApiConnectorSchema,
  invocationPolicies: invocationPolicyListResponseSchema
});

export type OpenApiConnectorDetailBundle = {
  connector: OpenApiConnectorListItem;
  invocationPolicies: InvocationPolicyTool[];
};

export class OpenApiConnectorDetailsBrowserRoute {
  constructor(private readonly request: typeof globalThis.fetch = globalThis.fetch) {}

  async get(connectorId: string, signal?: AbortSignal): Promise<OpenApiConnectorDetailBundle> {
    const response = await fetchResponse(this.request, `/admin/openapi-connectors/data/connectors/${encodeURIComponent(connectorId)}`, { signal });
    if (!response.ok) throw new BrowserRequestError(response.status);
    const payload = openApiConnectorDetailBundleSchema.parse(await response.json());
    return { connector: mapOpenApiConnector(payload.connector), invocationPolicies: payload.invocationPolicies.tools };
  }
}
