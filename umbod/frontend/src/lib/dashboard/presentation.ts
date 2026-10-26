import type { CatalogueConnector } from './domain/schemas';

export const connectorKindLabels: Record<CatalogueConnector['kind'], string> = {
  native: 'Native',
  openapi: 'OpenAPI',
  downstream_mcp: 'MCP server'
};

export function catalogueConnectorId(connector: CatalogueConnector): string {
  return `${connector.kind}:${connector.connector_id}`;
}

export function catalogueSidebarItem(connector: CatalogueConnector): CatalogueConnector & { id: string; name: string } {
  return { ...connector, id: catalogueConnectorId(connector), name: connector.display_name };
}
