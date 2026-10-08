import { render } from 'svelte/server';
import { describe, expect, test, vi } from 'vitest';
import { loadOpenApiConnectorList } from '$lib/admin/openapi-connectors-api';
import ImportCatalogPanel from '$lib/components/admin/openapi-connectors/ImportCatalogPanel.svelte';
import { ImportCatalogState } from '$lib/components/admin/openapi-connectors/import-catalog-state.svelte';

const catalogImport = {
  connector_id: 'billing',
  catalog_id: 'cat-3',
  operation_ids: ['listInvoices'],
  approved_hosts: ['api.example.com'],
  selected_server_url: 'https://api.example.com',
  imported_at: '2026-03-03T09:00:00Z'
};

describe('OpenAPI connector administration milestone 3', () => {
  test('file import accepts a valid hostname entered without adding a hostname chip', () => {
    const state = new ImportCatalogState();
    state.selectFiles([new File(['{}'], 'api.json', { type: 'application/json' })]);
    state.setHostInput('api.example.com');

    expect(state.beginFileSubmit()).toBe(true);
    expect(state.hostError).toBe('');
  });

  test('URL import accepts a valid hostname entered without adding a hostname chip', () => {
    const state = new ImportCatalogState();
    state.setMode('url');
    state.setUrl('https://api.example.com/openapi.json');
    state.setHostInput('api.example.com');

    expect(state.beginUrlSubmit()).toBe(true);
    expect(state.hostError).toBe('');
  });

  test('file import submits the hostname currently entered in the visible field', () => {
    const { body } = render(ImportCatalogPanel, { props: { connectorId: 'billing' } });

    expect(body).toMatch(/id="approved-host-file"[^>]*name="approved_hosts"/);
  });

  test('URL import submits the hostname currently entered in the visible field', () => {
    const { body } = render(ImportCatalogPanel, {
      props: {
        connectorId: 'billing',
        action: {
          status: 'invalid',
          mode: 'url',
          message: 'Retry the import',
          url: 'https://api.example.com/openapi.json'
        }
      }
    });

    expect(body).toMatch(/id="approved-host-url"[^>]*name="approved_hosts"/);
  });

  test('the connector list loads without requesting tools', async () => {
    const connectors = {
      list: vi.fn(async () => ({ connectors: [{
        connector_id: 'billing',
        display_name: 'Billing',
        tool_name_prefix: 'Billing',
        capability_description: 'Manage billing resources',
        created_at: '2026-03-03T09:00:00Z',
        updated_at: '2026-03-03T09:00:00Z',
        publication_status: 'draft' as const,
        available_actions: ['import', 'publish'] as Array<'import' | 'publish'>
      }] })),
      listTools: vi.fn(async () => ({ tools: [] }))
    };

    await expect(loadOpenApiConnectorList({ connectors })).resolves.toMatchObject({
      status: 'ready',
      connectors: [{ id: 'billing', tools: [] }]
    });
    expect(connectors.listTools).not.toHaveBeenCalled();
  });

  test('a tool failure cannot fail a multiple-connector list page', async () => {
    const connectors = {
      list: vi.fn(async () => ({ connectors: ['billing', 'identity'].map((connectorId) => ({
        connector_id: connectorId,
        display_name: connectorId,
        tool_name_prefix: connectorId,
        capability_description: `Manage ${connectorId} resources`,
        created_at: '2026-03-03T09:00:00Z',
        updated_at: '2026-03-03T09:00:00Z',
        publication_status: 'draft' as const,
        available_actions: ['import', 'publish'] as Array<'import' | 'publish'>
      })) })),
      listTools: vi.fn(async (connectorId: string) => {
        if (connectorId === 'identity') throw new Error('tools unavailable');
        return { tools: [] };
      })
    };

    await expect(loadOpenApiConnectorList({ connectors })).resolves.toMatchObject({
      status: 'ready',
      connectors: [{ id: 'billing' }, { id: 'identity' }]
    });
    expect(connectors.listTools).not.toHaveBeenCalled();
  });

  test('initial loading does not turn an unavailable operation catalog into an empty result', async () => {
    const connectors = {
      list: vi.fn(async () => ({
        connectors: [{
          connector_id: 'billing',
          display_name: 'Billing',
          tool_name_prefix: 'Billing',
          capability_description: 'Manage billing resources',
          created_at: '2026-03-03T09:00:00Z',
          updated_at: '2026-03-03T09:00:00Z',
          publication_status: 'draft' as const,
          available_actions: ['import', 'publish'] as Array<'import' | 'publish'>
        }]
      })),
      listTools: vi.fn(async () => { throw new Error('tools unavailable'); })
    };

    await expect(loadOpenApiConnectorList({ connectors })).resolves.toMatchObject({
      status: 'ready',
      connectors: [{ id: 'billing', tools: [] }]
    });
    expect(connectors.listTools).not.toHaveBeenCalled();
  });

});
