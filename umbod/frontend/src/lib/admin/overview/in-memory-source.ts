import type { OverviewSource } from './port';
import { available, overviewConnectorSchema, overviewToolSchema, type Available, type ConnectorKind, type OverviewConnector, type OverviewTool } from './models';

export type InMemoryOverviewData = {
  connectors: Record<ConnectorKind, Available<OverviewConnector[]>>;
  tools: Record<ConnectorKind, Record<string, Available<OverviewTool[]>>>;
  permissionGroups: Available<number>;
};

export class InMemoryOverviewSource implements OverviewSource {
  constructor(private readonly data: InMemoryOverviewData) {}

  async listConnectors(kind: ConnectorKind): Promise<Available<OverviewConnector[]>> {
    const result = this.data.connectors[kind];
    return result.status === 'available' ? available(overviewConnectorSchema.array().parse(result.value)) : result;
  }

  async listTools(kind: ConnectorKind, connectorId: string): Promise<Available<OverviewTool[]>> {
    const result = this.data.tools[kind][connectorId];
    if (result === undefined) throw new Error(`Missing tool fixture for ${kind}/${connectorId}`);
    return result.status === 'available' ? available(overviewToolSchema.array().parse(result.value)) : result;
  }

  async countPermissionGroups(): Promise<Available<number>> {
    return this.data.permissionGroups;
  }
}
