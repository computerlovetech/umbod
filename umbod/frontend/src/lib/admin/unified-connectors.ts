import { connectorCapabilities } from './connector-capabilities.js';
import { mapConnectorApiItem, type ConnectorListItem } from './connectors.js';
import type { DownstreamMcpConnectorSummary } from './downstream-mcp-connectors.js';
import type { AdminApi } from './infrastructure/admin-api.js';
import { isOperationalError, SchemaValidationError } from './infrastructure/transport.js';
import { loadOpenApiConnectorList } from './openapi-connectors-api.js';
import type { OpenApiConnectorListItem, OpenApiConnectorListPageData } from './openapi-connectors.js';

export type UnifiedConnectorKind = 'native' | 'openapi' | 'mcp';

export const connectorWorkspacePaths: Readonly<Record<UnifiedConnectorKind, string>> = {
  native: '/admin/connectors',
  openapi: '/admin/openapi-connectors',
  mcp: '/admin/downstream-mcp-connectors'
};

export function connectorWorkspaceHref(row: Pick<UnifiedConnectorRow, 'kind' | 'id'>, requestedCapability: string | null): string {
  const query = new URLSearchParams({ connector: row.id });
  const capability = connectorCapabilities.find((value) => value === requestedCapability);
  if (capability) query.set('capability', capability);
  return `${connectorWorkspacePaths[row.kind]}?${query}`;
}

export type UnifiedConnectorRow = Readonly<{
  kind: UnifiedConnectorKind;
  id: string;
  name: string;
  status: string;
  iconDataUrl?: string;
}>;

export type UnifiedConnectorInventory = {
  unifiedRows: readonly UnifiedConnectorRow[];
  unavailableKinds: readonly UnifiedConnectorKind[];
  nativeAvailable: boolean;
};

type InventoryApi = {
  connectors: { connectors: Pick<AdminApi['connectors']['connectors'], 'list'> };
  openApiConnectors: { connectors: Pick<AdminApi['openApiConnectors']['connectors'], 'list'> };
  downstreamMcpConnectors: Pick<AdminApi['downstreamMcpConnectors'], 'list'>;
};

type ConnectorInventory<Item> =
  | { status: 'available'; connectors: Item[] }
  | { status: 'failed'; connectors: [] };

function isInventoryResponseFailure(error: unknown): boolean {
  return isOperationalError(error) || error instanceof SyntaxError || (error instanceof SchemaValidationError && error.direction === 'inbound');
}

async function readOpenApiInventory(api: InventoryApi['openApiConnectors']): Promise<OpenApiConnectorListPageData> {
  try {
    return await loadOpenApiConnectorList(api);
  } catch (error) {
    if (!isInventoryResponseFailure(error)) throw error;
    return { status: 'failed', connectors: [] };
  }
}

async function readInventory<Item>(load: () => Promise<Item[]>): Promise<ConnectorInventory<Item>> {
  try {
    return { status: 'available', connectors: await load() };
  } catch (error) {
    if (!isInventoryResponseFailure(error)) throw error;
    return { status: 'failed', connectors: [] };
  }
}

function compareConnectorNames(left: { name: string }, right: { name: string }): number {
  return left.name.localeCompare(right.name);
}

export async function loadUnifiedConnectorInventory(api: InventoryApi): Promise<{
  native: ConnectorInventory<ConnectorListItem>;
  openapi: OpenApiConnectorListPageData;
  mcp: ConnectorInventory<DownstreamMcpConnectorSummary>;
  inventory: UnifiedConnectorInventory;
}> {
  const [native, openapi, mcp] = await Promise.all([
    readInventory(async () => (await api.connectors.connectors.list()).connectors.map(mapConnectorApiItem)),
    readOpenApiInventory(api.openApiConnectors),
    readInventory(async () => (await api.downstreamMcpConnectors.list()).connectors)
  ]);
  const unavailableKinds: UnifiedConnectorKind[] = [];
  if (native.status === 'failed') unavailableKinds.push('native');
  if (openapi.status === 'failed') unavailableKinds.push('openapi');
  if (mcp.status === 'failed') unavailableKinds.push('mcp');
  const unifiedRows = [
    ...native.connectors.filter((connector) => connector.isConfigured).map(nativeRow),
    ...(openapi.status === 'ready' ? openapi.connectors.map(openApiRow) : []),
    ...mcp.connectors.map(mcpRow)
  ].sort(compareConnectorNames);
  return { native, openapi, mcp, inventory: { unifiedRows, unavailableKinds, nativeAvailable: native.connectors.some((connector) => !connector.isConfigured) } };
}

function nativeRow({ id, name, publicationStatus, iconDataUrl }: ConnectorListItem): UnifiedConnectorRow {
  return { kind: 'native', id, name, status: publicationStatus, iconDataUrl };
}

function openApiRow({ id, name, publicationStatus }: OpenApiConnectorListItem): UnifiedConnectorRow {
  return { kind: 'openapi', id, name, status: publicationStatus };
}

function mcpRow(connector: DownstreamMcpConnectorSummary): UnifiedConnectorRow {
  return {
    kind: 'mcp', id: connector.connector_id, name: connector.display_name,
    status: connector.publication_status === 'published' ? 'Published' : 'Unpublished',
    iconDataUrl: connector.icon_url || undefined
  };
}
