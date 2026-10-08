import type { AdminApi } from '../infrastructure/admin-api';
import { HttpError, isOperationalError } from '../infrastructure/transport';
import type { OverviewSource } from './port';
import { available, overviewConnectorSchema, overviewToolSchema, type Available, type ConnectorKind, type OverviewConnector, type OverviewTool } from './models';

async function operationalResult<T>(operation: () => Promise<T>): Promise<Available<T>> {
  try {
    return available(await operation());
  } catch (error) {
    if (error instanceof HttpError && (error.status === 401 || error.status === 403)) throw error;
    if (!isOperationalError(error)) throw error;
    return { status: 'unavailable' };
  }
}

export class ApiOverviewSource implements OverviewSource {
  constructor(private readonly api: AdminApi) {}

  async listConnectors(kind: ConnectorKind): Promise<Available<OverviewConnector[]>> {
    return operationalResult(async () => {
      if (kind === 'catalog') {
        const response = await this.api.connectors.connectors.list();
        return overviewConnectorSchema.array().parse(response.connectors.map((connector) => ({ id: connector.id, publicationStatus: connector.publication_status, discoveryStatus: 'unknown' })));
      }
      if (kind === 'openapi') {
        const response = await this.api.openApiConnectors.connectors.list();
        return overviewConnectorSchema.array().parse(response.connectors.map((connector) => ({ id: connector.connector_id, publicationStatus: connector.publication_status, discoveryStatus: 'unknown' })));
      }
      const response = await this.api.downstreamMcpConnectors.list();
      return overviewConnectorSchema.array().parse(response.connectors.map((connector) => ({ id: connector.connector_id, publicationStatus: connector.publication_status, discoveryStatus: connector.health.status })));
    });
  }

  async listTools(kind: ConnectorKind, connectorId: string): Promise<Available<OverviewTool[]>> {
    return operationalResult(async () => {
      const response = kind === 'catalog'
        ? await this.api.connectors.tools.listActivations(connectorId)
        : kind === 'openapi'
          ? await this.api.openApiConnectors.connectors.listActivations(connectorId)
          : await this.api.downstreamMcpConnectors.listActivations(connectorId);
      return overviewToolSchema.array().parse(response.tools.map((tool) => ({ activationStatus: tool.activation_status })));
    });
  }

  async countPermissionGroups(): Promise<Available<number>> {
    return operationalResult(async () => (await this.api.groupPermissions.permissions.list()).length);
  }
}
