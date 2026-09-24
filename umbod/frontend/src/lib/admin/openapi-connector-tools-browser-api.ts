import { BrowserRequestError, fetchResponse } from './infrastructure/browser-request';
import { mapOpenApiOperationTool, openApiOperationToolListResponseSchema, type OpenApiOperationToolUiModel } from './openapi-connectors';

export class OpenApiConnectorToolsBrowserRoute {
  constructor(private readonly request: typeof globalThis.fetch = globalThis.fetch) {}

  async list(connectorId: string): Promise<OpenApiOperationToolUiModel[]> {
    const response = await fetchResponse(this.request, `/admin/openapi-connectors/${encodeURIComponent(connectorId)}/tools`);
    if (!response.ok) throw new BrowserRequestError(response.status);
    const payload = openApiOperationToolListResponseSchema.parse(await response.json());
    return payload.tools.map(mapOpenApiOperationTool);
  }
}
