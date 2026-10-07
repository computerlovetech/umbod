import type { Available, ConnectorKind, OverviewConnector, OverviewTool } from './models';

export interface OverviewSource {
  listConnectors(kind: ConnectorKind): Promise<Available<OverviewConnector[]>>;
  listTools(kind: ConnectorKind, connectorId: string): Promise<Available<OverviewTool[]>>;
  countPermissionGroups(): Promise<Available<number>>;
}
