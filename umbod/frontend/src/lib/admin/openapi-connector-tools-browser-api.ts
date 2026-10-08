import { adminApi } from './infrastructure/admin-api';
import { browserRequest } from './infrastructure/browser-request';
import { mapOpenApiOperationTool, type OpenApiOperationToolUiModel } from './openapi-connectors';

export class OpenApiConnectorToolsBrowserRoute {
  constructor(private readonly request: typeof fetch = globalThis.fetch) {}
  async list(connectorId: string): Promise<OpenApiOperationToolUiModel[]> {
    return browserRequest(async () => (await adminApi(this.request).openApiConnectors.connectors.listTools(connectorId)).tools.map(mapOpenApiOperationTool));
  }
}
