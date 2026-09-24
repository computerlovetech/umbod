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

  test('typed hostname is trimmed and normalized at the action boundary', async () => {
    const { actions } = await import('../../routes/admin/openapi-connectors/+page.server');
    const fetchMock = vi.fn(async (_input: URL | RequestInfo, _init?: RequestInit) => new Response(JSON.stringify(catalogImport), { status: 201 }));
    const form = new FormData();
    form.append('connectorId', 'billing');
    form.append('document', JSON.stringify({ openapi: '3.1.0' }));
    form.append('approved_hosts', '  API.Example.COM  ');
    const request = new Request('http://frontend/admin/openapi-connectors?/importDocument', { method: 'POST', body: form });

    await expect(actions.importDocument({ fetch: fetchMock as unknown as typeof globalThis.fetch, request } as never)).rejects.toMatchObject({ status: 303 });
    expect(JSON.parse(String((fetchMock.mock.calls[0][1] as RequestInit).body)).approved_hosts).toEqual(['api.example.com']);
  });

  test('typed hostname duplicating an existing chip is forwarded once', async () => {
    const { actions } = await import('../../routes/admin/openapi-connectors/+page.server');
    const fetchMock = vi.fn(async (_input: URL | RequestInfo, _init?: RequestInit) => new Response(JSON.stringify(catalogImport), { status: 201 }));
    const form = new FormData();
    form.append('connectorId', 'billing');
    form.append('document', JSON.stringify({ openapi: '3.1.0' }));
    form.append('approved_hosts', 'api.example.com');
    form.append('approved_hosts', ' API.EXAMPLE.COM ');
    const request = new Request('http://frontend/admin/openapi-connectors?/importDocument', { method: 'POST', body: form });

    await expect(actions.importDocument({ fetch: fetchMock as unknown as typeof globalThis.fetch, request } as never)).rejects.toMatchObject({ status: 303 });
    expect(JSON.parse(String((fetchMock.mock.calls[0][1] as RequestInit).body)).approved_hosts).toEqual(['api.example.com']);
  });

  test('existing chip hosts and a distinct typed hostname are all forwarded', async () => {
    const { actions } = await import('../../routes/admin/openapi-connectors/+page.server');
    const fetchMock = vi.fn(async (_input: URL | RequestInfo, _init?: RequestInit) => new Response(JSON.stringify(catalogImport), { status: 201 }));
    const form = new FormData();
    form.append('connectorId', 'billing');
    form.append('document', JSON.stringify({ openapi: '3.1.0' }));
    form.append('approved_hosts', 'api.example.com');
    form.append('approved_hosts', 'auth.example.com');
    form.append('approved_hosts', 'files.example.com');
    const request = new Request('http://frontend/admin/openapi-connectors?/importDocument', { method: 'POST', body: form });

    await expect(actions.importDocument({ fetch: fetchMock as unknown as typeof globalThis.fetch, request } as never)).rejects.toMatchObject({ status: 303 });
    expect(JSON.parse(String((fetchMock.mock.calls[0][1] as RequestInit).body)).approved_hosts).toEqual([
      'api.example.com',
      'auth.example.com',
      'files.example.com'
    ]);
  });

  test('blank visible approved hostname is ignored when valid chips are submitted', async () => {
    const { actions } = await import('../../routes/admin/openapi-connectors/+page.server');
    const fetchMock = vi.fn(async (_input: URL | RequestInfo, _init?: RequestInit) => new Response(JSON.stringify(catalogImport), { status: 201 }));
    const form = new FormData();
    form.append('connectorId', 'billing');
    form.append('document', JSON.stringify({ openapi: '3.1.0' }));
    form.append('approved_hosts', '   ');
    form.append('approved_hosts', 'api.example.com');
    const request = new Request('http://frontend/admin/openapi-connectors?/importDocument', { method: 'POST', body: form });

    await expect(actions.importDocument({ fetch: fetchMock as unknown as typeof globalThis.fetch, request } as never)).rejects.toMatchObject({ status: 303 });
    expect(JSON.parse(String((fetchMock.mock.calls[0][1] as RequestInit).body)).approved_hosts).toEqual(['api.example.com']);
  });

  test('invalid typed hostname blocks submit when a valid chip exists', async () => {
    const { actions } = await import('../../routes/admin/openapi-connectors/+page.server');
    const fetchMock = vi.fn();
    const form = new FormData();
    form.append('connectorId', 'billing');
    form.append('document', JSON.stringify({ openapi: '3.1.0' }));
    form.append('approved_hosts', 'api.example.com');
    form.append('approved_hosts', 'https://invalid.example.com');
    const request = new Request('http://frontend/admin/openapi-connectors?/importDocument', { method: 'POST', body: form });

    await expect(actions.importDocument({ fetch: fetchMock, request } as never)).resolves.toMatchObject({
      status: 'invalid',
      message: expect.stringMatching(/hostnames/i)
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  test('all-blank approved hostnames return the invalid hostname response without fetching', async () => {
    const { actions } = await import('../../routes/admin/openapi-connectors/+page.server');
    const fetchMock = vi.fn();
    const form = new FormData();
    form.append('connectorId', 'billing');
    form.append('document', JSON.stringify({ openapi: '3.1.0' }));
    form.append('approved_hosts', '');
    form.append('approved_hosts', '   ');
    const request = new Request('http://frontend/admin/openapi-connectors?/importDocument', { method: 'POST', body: form });

    await expect(actions.importDocument({ fetch: fetchMock, request } as never)).resolves.toMatchObject({
      status: 'invalid',
      mode: 'url',
      connectorId: 'billing',
      approvedHosts: [],
      message: 'Add at least one exact hostname.',
      retryable: false
    });
    expect(fetchMock).not.toHaveBeenCalled();
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

  test('file action forwards multipart and redirects to the list workspace', async () => {
    const { actions } = await import('../../routes/admin/openapi-connectors/+page.server');
    const fetchMock = vi.fn(async (_input: URL | RequestInfo, _init?: RequestInit) => new Response(JSON.stringify(catalogImport), { status: 201 }));
    const fetch = fetchMock as unknown as typeof globalThis.fetch;
    const form = new FormData();
    form.append('connectorId', 'billing');
    form.append('file', new File(['{}'], 'api.json', { type: 'application/json' }));
    form.append('approved_hosts', 'api.example.com');
    const request = new Request('http://frontend/admin/openapi-connectors?/importFile', {
      method: 'POST',
      body: form,
      headers: { authorization: 'Bearer admin' }
    });
    await expect(actions.importFile({ fetch, request } as never)).rejects.toMatchObject({
      status: 303,
      location: '/admin/openapi-connectors?connector=billing&imported=true'
    });
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(init.body).toBeInstanceOf(FormData);
    expect(new Headers(init.headers).has('content-type')).toBe(false);
  });

  test('document action validates payload and posts JSON import without import-url', async () => {
    const { actions } = await import('../../routes/admin/openapi-connectors/+page.server');
    const missingHosts = new FormData();
    missingHosts.append('connectorId', 'billing');
    missingHosts.append('document', JSON.stringify({ openapi: '3.1.0' }));
    missingHosts.append('url', 'https://example.com/spec.json');
    const invalid = new Request('http://frontend/admin/openapi-connectors?/importDocument', {
      method: 'POST',
      body: missingHosts
    });
    await expect(actions.importDocument({ fetch: vi.fn(), request: invalid } as never)).resolves.toMatchObject({
      status: 'invalid',
      mode: 'url',
      message: expect.stringMatching(/hostname/)
    });

    const fetchMock = vi.fn(async (_input: URL | RequestInfo, _init?: RequestInit) => new Response(JSON.stringify(catalogImport), { status: 201 }));
    const form = new FormData();
    form.append('connectorId', 'billing');
    form.append('document', JSON.stringify({ openapi: '3.1.0', info: { title: 'Billing' } }));
    form.append('approved_hosts', 'api.example.com');
    form.append('url', 'https://api.example.com/openapi.json');
    const request = new Request('http://frontend/admin/openapi-connectors?/importDocument', {
      method: 'POST',
      body: form,
      headers: { authorization: 'Bearer admin' }
    });
    await expect(
      actions.importDocument({ fetch: fetchMock as unknown as typeof globalThis.fetch, request } as never)
    ).rejects.toMatchObject({
      status: 303,
      location: '/admin/openapi-connectors?connector=billing&imported=true'
    });
    expect(String(fetchMock.mock.calls[0][0])).toContain('/connectors/openapi/billing/import');
    expect(String(fetchMock.mock.calls[0][0])).not.toContain('import-url');
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(String(init.body))).toEqual({
      document: { openapi: '3.1.0', info: { title: 'Billing' } },
      approved_hosts: ['api.example.com']
    });
  });
});
