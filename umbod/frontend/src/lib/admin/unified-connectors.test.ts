import { describe, expect, test } from 'vitest';
import { type ConnectorApiItem } from './connectors.js';
import { HttpError, SchemaValidationError } from './infrastructure/transport.js';
import { summaryFixture } from './personal-mcp-servers/fixtures.test-support.js';
import { connectorWorkspaceHref, loadUnifiedConnectorInventory } from './unified-connectors.js';
import { submittedConnector } from './portable-connectors/fixtures.test-support.js';

type InventoryApi = Parameters<typeof loadUnifiedConnectorInventory>[0];

function nativeConnector(id: string, name: string, status: ConnectorApiItem['publication_status']): ConnectorApiItem {
  return { id, display_name: name, description: 'Connector', extension: { source: 'built-in' }, publication_status: status, available_actions: [] };
}

function inventoryApi(overrides: Partial<InventoryApi>): InventoryApi {
  return {
    connectors: { connectors: { list: async () => ({ connectors: [] }) } },
    openApiConnectors: { connectors: { list: async () => ({ connectors: [] }) } },
    downstreamMcpConnectors: { list: async () => ({ connectors: [] }) },
    portableConnectors: { list: async () => ({ connectors: [] }) },
    ...overrides
  };
}

describe('loadUnifiedConnectorInventory', () => {
  test('sorts the mixed inventory and reserves unconfigured native connectors for setup', async (): Promise<void> => {
    const api = inventoryApi({
      connectors: { connectors: { list: async () => ({ connectors: [nativeConnector('same', 'Zulu', 'published'), nativeConnector('setup', 'Setup', 'unconfigured')] }) } },
      openApiConnectors: { connectors: { list: async () => ({ connectors: [{ connector_id: 'same', display_name: 'Alpha', publication_status: 'draft', available_actions: [] }] }) } },
      downstreamMcpConnectors: { list: async () => ({ connectors: [{ ...summaryFixture('same'), display_name: 'Middle', icon_url: 'https://example.com/icon.svg' }] }) }
    });
    const { inventory, native } = await loadUnifiedConnectorInventory(api);
    expect(inventory).toEqual({
      unifiedRows: [
        { kind: 'openapi', id: 'same', name: 'Alpha', status: 'Draft' },
        { kind: 'mcp', id: 'same', name: 'Middle', status: 'Unpublished', iconDataUrl: 'https://example.com/icon.svg' },
        { kind: 'native', id: 'same', name: 'Zulu', status: 'Published' }
      ],
      unavailableKinds: [], nativeAvailable: true
    });
    expect(native.connectors.map((connector) => connector.id)).toEqual(['same', 'setup']);
  });

  test('reports operational failure without losing available rows', async (): Promise<void> => {
    const api = inventoryApi({
      connectors: { connectors: { list: async () => { throw new HttpError(503, 'Unavailable', {}); } } },
      downstreamMcpConnectors: { list: async () => ({ connectors: [summaryFixture()] }) }
    });
    const { inventory } = await loadUnifiedConnectorInventory(api);
    expect(inventory.unavailableKinds).toEqual(['native']);
    expect(inventory.nativeAvailable).toBe(false);
    expect(inventory.unifiedRows.map((row) => row.kind)).toEqual(['mcp']);
  });

  test('isolates invalid upstream payloads without losing healthy inventory', async (): Promise<void> => {
    const api = inventoryApi({
      connectors: { connectors: { list: async () => ({ connectors: [nativeConnector('native', 'Native', 'published')] }) } },
      openApiConnectors: { connectors: { list: async () => { throw new SyntaxError('Invalid JSON'); } } },
      downstreamMcpConnectors: { list: async () => { throw new SchemaValidationError('inbound', []); } }
    });
    const { inventory } = await loadUnifiedConnectorInventory(api);
    expect(inventory.unavailableKinds).toEqual(['openapi', 'mcp']);
    expect(inventory.unifiedRows.map((row) => row.name)).toEqual(['Native']);
  });

  test('lists a submitted connector before configuration and links directly to its form', async (): Promise<void> => {
    const api = inventoryApi({ portableConnectors: { list: async () => ({ connectors: [submittedConnector] }) } });
    const { inventory } = await loadUnifiedConnectorInventory(api);
    expect(inventory.unifiedRows).toEqual([{
      kind: 'portable', id: submittedConnector.connector_id, name: submittedConnector.name,
      description: submittedConnector.description, status: 'Inactive', configured: false
    }]);
    const [row] = inventory.unifiedRows;
    expect(connectorWorkspaceHref(row, 'tools')).toBe(`/admin/portable-connectors?connector=${submittedConnector.connector_id}`);
  });

  test('a portable connector lookup failure leaves the available kinds intact', async (): Promise<void> => {
    const api = inventoryApi({
      connectors: { connectors: { list: async () => ({ connectors: [nativeConnector('native', 'Native', 'published')] }) } },
      portableConnectors: { list: async () => { throw new HttpError(503, 'Unavailable', {}); } }
    });
    const { inventory } = await loadUnifiedConnectorInventory(api);
    expect(inventory.unavailableKinds).toEqual(['portable']);
    expect(inventory.unifiedRows.map((row) => row.kind)).toEqual(['native']);
  });

  test('propagates unexpected inventory errors', async (): Promise<void> => {
    const error = new Error('Unexpected');
    const api = inventoryApi({ downstreamMcpConnectors: { list: async () => { throw error; } } });
    await expect(loadUnifiedConnectorInventory(api)).rejects.toBe(error);
  });
});
