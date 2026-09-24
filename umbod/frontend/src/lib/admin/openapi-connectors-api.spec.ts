import { describe, expect, test, vi } from 'vitest';
import { HttpError, SchemaValidationError, serverTransport, type Transport, type TransportRequest } from './infrastructure/transport';
import { createOpenApiConnectorRequestSchema, openApiConnectorListResponseSchema, openApiConnectorSchema } from './openapi-connectors';
import {
  InMemoryOpenApiConnectorApi,
  loadOpenApiConnectorDetail,
  loadOpenApiConnectorList,
  OpenApiConnectorsApi,
  setOpenApiPublication
} from './openapi-connectors-api';

function recordingTransport(): { transport: Transport; calls: TransportRequest<unknown>[] } {
  const calls: TransportRequest<unknown>[] = [];
  return {
    transport: { async request(opts) { calls.push(opts as TransportRequest<unknown>); return undefined as never; } },
    calls
  };
}

function connectorFixture(overrides: Record<string, unknown> = {}) {
  return {
    connector_id: 'billing',
    display_name: 'Billing API',
    tool_name_prefix: 'Billing_API',
    capability_description: 'Manage billing',
    base_capability_description: 'Manage billing',
    effective_capability_description: 'Manage billing',
    capability_description_override: { state: 'system', revision: 0 },
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-02T00:00:00Z',
    publication_status: 'unpublished',
    available_actions: ['import', 'publish'],
    ...overrides
  };
}

function connectorSummaryFixture(overrides: Record<string, unknown> = {}) {
  const detail = connectorFixture(overrides);
  return {
    connector_id: detail.connector_id,
    display_name: detail.display_name,
    publication_status: detail.publication_status,
    available_actions: detail.available_actions
  };
}

function apiFrom(body: unknown, status = 200): OpenApiConnectorsApi {
  const fetch = vi.fn(async () => new Response(JSON.stringify(body), { status }));
  return new OpenApiConnectorsApi(serverTransport(fetch as unknown as typeof globalThis.fetch));
}

describe('OpenApiConnectorsApi connector-list contract', () => {
  test('validates capability description in create payloads', () => {
    expect(createOpenApiConnectorRequestSchema.parse({ display_name: 'Inventory', tool_name_prefix: 'Inventory', capability_description: 'Search inventory' })).toEqual({
      display_name: 'Inventory', tool_name_prefix: 'Inventory', capability_description: 'Search inventory'
    });
    expect(() => createOpenApiConnectorRequestSchema.parse({ display_name: 'Inventory', tool_name_prefix: 'Inventory', capability_description: '   ' })).toThrow();
    expect(() => createOpenApiConnectorRequestSchema.parse({ display_name: 'Inventory', tool_name_prefix: 'Inventory', capability_description: 'x'.repeat(301) })).toThrow();
  });
  test('lists the bounded OpenAPI connector collection through a validated route', () => {
    const { transport, calls } = recordingTransport();
    new OpenApiConnectorsApi(transport).connectors.list();
    expect(calls[0]).toMatchObject({ method: 'GET', path: '/admin/connectors/openapi' });
    expect(calls[0].outputSchema).toBeDefined();
  });

  test('maps publication status and available actions defensively', async () => {
    const fetch = vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith('/tools')) {
        return new Response(JSON.stringify({ tools: [] }), { status: 200 });
      }
      return new Response(JSON.stringify({ connectors: [
        connectorSummaryFixture({ connector_id: 'unconfigured', display_name: 'Unconfigured API', publication_status: 'unconfigured', available_actions: ['import'] }),
        connectorSummaryFixture({ connector_id: 'draft', display_name: 'Draft API', publication_status: 'draft', available_actions: ['import', 'publish'] }),
        connectorSummaryFixture({ connector_id: 'published', display_name: 'Published API', publication_status: 'published', available_actions: ['import', 'unpublish'] }),
        connectorSummaryFixture({ connector_id: 'unpublished', display_name: 'Unpublished API', publication_status: 'unpublished', available_actions: ['import', 'publish'] })
      ] }), { status: 200 });
    }) as typeof globalThis.fetch;
    const data = await loadOpenApiConnectorList(new OpenApiConnectorsApi(serverTransport(fetch)));
    expect(data).toMatchObject({ status: 'ready', connectors: [
      { id: 'unconfigured', name: 'Unconfigured API', publicationStatus: 'Unconfigured', canPublish: false, canUnpublish: false, canImport: true, tools: [] },
      { id: 'draft', name: 'Draft API', publicationStatus: 'Draft', canPublish: true, canUnpublish: false, canImport: true, tools: [] },
      { id: 'published', name: 'Published API', publicationStatus: 'Published', canPublish: false, canUnpublish: true, canImport: true, tools: [] },
      { id: 'unpublished', name: 'Unpublished API', publicationStatus: 'Unpublished', canPublish: true, canUnpublish: false, canImport: true, tools: [] }
    ] });
  });

  test('does not fetch tools while mapping list items', async () => {
    const tools = {
      tools: [
        { operation_id: 'listInvoices', method: 'get', path: '/invoices', summary: 'List', description: 'Lists invoices', activation_status: 'disabled', parameters: { type: 'object', properties: {}, required: [] } }
      ]
    };
    const fetch = vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith('/tools')) return new Response(JSON.stringify(tools), { status: 200 });
      return new Response(JSON.stringify({ connectors: [connectorSummaryFixture()] }), { status: 200 });
    }) as typeof globalThis.fetch;
    const data = await loadOpenApiConnectorList(new OpenApiConnectorsApi(serverTransport(fetch)));
    expect(data).toMatchObject({
      status: 'ready',
      connectors: [{
        id: 'billing',
        createdAt: '',
        updatedAt: '',
        tools: []
      }]
    });
    expect(fetch).toHaveBeenCalledOnce();
  });

  test('list and get parse distinct strict schemas while detail retains detail fields', () => {
    const detail = connectorFixture();
    const summary = connectorSummaryFixture();
    expect(openApiConnectorListResponseSchema.parse({ connectors: [summary] }).connectors[0]).toEqual(summary);
    expect(openApiConnectorListResponseSchema.safeParse({ connectors: [detail] }).success).toBe(false);
    expect(openApiConnectorSchema.parse(detail)).toMatchObject({
      tool_name_prefix: 'Billing_API',
      capability_description: 'Manage billing',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-02T00:00:00Z'
    });
  });

  test('returns empty state and exposes malformed contracts', async () => {
    await expect(loadOpenApiConnectorList(apiFrom({ connectors: [] }))).resolves.toMatchObject({ status: 'empty' });
    await expect(loadOpenApiConnectorList(apiFrom({ connectors: [{ connector_id: 'bad' }] }))).rejects.toBeInstanceOf(SchemaValidationError);
  });

  test('creates, gets, and lists tools with validated bounded contracts', () => {
    const { transport, calls } = recordingTransport();
    const route = new OpenApiConnectorsApi(transport).connectors;
    void route.create({ display_name: 'Billing API', tool_name_prefix: 'Billing_API', capability_description: 'Manage billing' });
    void route.get('billing');
    void route.listTools('billing');
    expect(calls.map(({ method, path }) => ({ method, path }))).toEqual([
      { method: 'POST', path: '/admin/connectors/openapi' },
      { method: 'GET', path: '/admin/connectors/openapi/billing' },
      { method: 'GET', path: '/admin/connectors/openapi/billing/tools' }
    ]);
    expect(calls[0].inputSchema).toBeDefined();
    expect(calls.every((call) => call.outputSchema !== undefined)).toBe(true);
  });

  test('imports file and document catalogs through validated bounded contracts', () => {
    const { transport, calls } = recordingTransport();
    const imports = new OpenApiConnectorsApi(transport).imports;
    const form = new FormData();
    form.append('file', new File(['{}'], 'api.json', { type: 'application/json' }));
    form.append('approved_hosts', 'api.example.com');
    void imports.importMultipart('billing', form, ['api.example.com']);
    void imports.importJson('billing', { document: { openapi: '3.1.0' }, approved_hosts: ['api.example.com'] });
    expect(calls.map(({ method, path }) => ({ method, path }))).toEqual([
      { method: 'POST', path: '/admin/connectors/openapi/billing/imports' },
      { method: 'POST', path: '/admin/connectors/openapi/billing/imports' }
    ]);
    expect(calls[0].requestBody).toMatchObject({ kind: 'multipart', metadata: { approved_hosts: ['api.example.com'] } });
    expect(calls[1].requestBody).toMatchObject({ kind: 'json', value: { document: { openapi: '3.1.0' }, approved_hosts: ['api.example.com'] } });
  });

  test('gets and updates masked Bearer configuration through validated contracts', () => {
    const { transport, calls } = recordingTransport();
    const route = new OpenApiConnectorsApi(transport).connectors;
    void route.getConfiguration('billing/id');
    void route.putConfiguration('billing/id', { authentication_type: 'bearer', bearer_token: 'private-token' });
    expect(calls.map(({ method, path }) => ({ method, path }))).toEqual([
      { method: 'GET', path: '/admin/connectors/openapi/billing%2Fid/configuration' },
      { method: 'PUT', path: '/admin/connectors/openapi/billing%2Fid/configuration' }
    ]);
    expect(calls[1].body).toEqual({ authentication_type: 'bearer', bearer_token: 'private-token' });
    expect(calls[1].inputSchema).toBeDefined();
    expect(calls.every((call) => call.outputSchema)).toBe(true);
  });

  test('saves ordered batch activations through encoded validated contracts', async () => {
    const { transport, calls } = recordingTransport();
    const route = new OpenApiConnectorsApi(transport).connectors;
    void route.saveActivations('billing/id', [
      { toolId: 'createInvoice', activationStatus: 'disabled', invocationMode: 'ask', expectedPolicyRevision: 2 },
      { toolId: 'listInvoices', invocationMode: 'direct', expectedPolicyRevision: 0 }
    ]);
    expect(calls[0]).toMatchObject({
      method: 'PUT',
      path: '/admin/connectors/openapi/billing%2Fid/tools/activation',
      body: { tools: [
        { tool_id: 'createInvoice', activation_status: 'disabled', invocation_mode: 'ask', expected_policy_revision: 2 },
        { tool_id: 'listInvoices', invocation_mode: 'direct', expected_policy_revision: 0 }
      ] }
    });
    expect(calls[0].inputSchema).toBeDefined();
    expect(calls[0].outputSchema).toBeDefined();
    expect(calls[0].path).not.toContain('invocation-policy');

    const memory = new InMemoryOpenApiConnectorApi(connectorFixture(), { tools: [
      { operation_id: 'first', method: 'GET', path: '/first', summary: 'First', description: 'First', activation_status: 'disabled', parameters: {}, output_schema_status: 'absent' },
      { operation_id: 'second', method: 'GET', path: '/second', summary: 'Second', description: 'Second', activation_status: 'enabled', parameters: {}, output_schema_status: 'absent' }
    ] });
    await expect(memory.saveActivations('billing', [
      { toolId: 'second', activationStatus: 'disabled' },
      { toolId: 'first', activationStatus: 'enabled' }
    ])).resolves.toEqual({ connector_id: 'billing', tools: [
      { tool_id: 'second', activation_status: 'disabled', invocation_mode: 'direct', policy_revision: 0 },
      { tool_id: 'first', activation_status: 'enabled', invocation_mode: 'direct', policy_revision: 0 }
    ] });
  });

  test('rejects malformed batch activation requests and responses at transport boundaries', async () => {
    const fetchForInvalidInput = vi.fn();
    const invalidInputApi = new OpenApiConnectorsApi(serverTransport(fetchForInvalidInput as unknown as typeof globalThis.fetch));
    await expect(invalidInputApi.connectors.saveActivations('billing', [])).rejects.toThrow();
    expect(fetchForInvalidInput).not.toHaveBeenCalled();

    const invalidResponseApi = apiFrom({ connector_id: 'billing', tools: [{ tool_id: 'listInvoices', activation_status: 'invalid' }] });
    await expect(invalidResponseApi.connectors.saveActivations('billing', [{ toolId: 'listInvoices', activationStatus: 'enabled' }])).rejects.toThrow();
  });

  test('exposes only batch tool activation and validated publication contracts', () => {
    const { transport, calls } = recordingTransport();
    const api = new OpenApiConnectorsApi(transport);
    void api.connectors.saveActivations('billing', [
      { toolId: 'listInvoices', activationStatus: 'enabled' }
    ]);
    void api.connectors.publish('billing');
    void api.connectors.unpublish('billing');
    expect('enableTool' in api.connectors).toBe(false);
    expect('disableTool' in api.connectors).toBe(false);
    expect(calls.map(({ method, path }) => ({ method, path }))).toEqual([
      { method: 'PUT', path: '/admin/connectors/openapi/billing/tools/activation' },
      { method: 'PUT', path: '/admin/connectors/openapi/billing/publication' },
      { method: 'DELETE', path: '/admin/connectors/openapi/billing/publication' }
    ]);
    expect(calls.every((call) => call.outputSchema)).toBe(true);
  });

  test('maps stale publication errors without exposing raw payloads', async () => {
    await expect(setOpenApiPublication(apiFrom({ detail: { code: 'openapi_connector_not_found' } }, 404), 'billing', 'unpublished')).resolves.toMatchObject({ status: 'stale' });
  });

  test('maps connector detail with tools and publication using an in-memory adapter', async () => {
    const connector = connectorFixture({ publication_status: 'published', available_actions: ['import', 'unpublish'] });
    const tools = {
      tools: [
        { operation_id: 'listInvoices', method: 'get', path: '/invoices', summary: 'List', description: 'Lists invoices', activation_status: 'disabled', parameters: { type: 'object', properties: {}, required: [] }, output_schema_status: 'absent' },
        { operation_id: 'createInvoice', method: 'post', path: '/invoices', summary: 'Create', description: 'Creates invoices', activation_status: 'enabled', parameters: { type: 'object', properties: {}, required: [] }, output_schema_status: 'present', output_schema: {} }
      ]
    };
    const api = new InMemoryOpenApiConnectorApi(connector, tools);
    await expect(loadOpenApiConnectorDetail({ connectors: api }, 'billing')).resolves.toMatchObject({
      status: 'ready',
      publicationStatus: 'Published',
      canPublish: false,
      canUnpublish: true,
      tools: [
        { operationId: 'listInvoices', method: 'get', path: '/invoices', activationStatus: 'disabled' },
        { operationId: 'createInvoice', method: 'post', path: '/invoices', activationStatus: 'enabled' }
      ]
    });
  });
});

describe('InMemoryOpenApiConnectorApi activation capability', () => {
  function activationApi(): InMemoryOpenApiConnectorApi {
    return new InMemoryOpenApiConnectorApi(connectorFixture({ connector_id: 'connector-1', publication_status: 'draft', available_actions: ['publish'] }), { tools: [
      { operation_id: 'first', method: 'GET', path: '/first', summary: 'First', description: 'First', activation_status: 'disabled', parameters: {}, output_schema_status: 'absent' },
      { operation_id: 'second', method: 'POST', path: '/second', summary: 'Second', description: 'Second', activation_status: 'enabled', parameters: {}, output_schema_status: 'absent' }
    ] });
  }

  test('persists activation and policy changes and returns request order', async () => {
    const api = activationApi();
    const result = await api.saveActivations('connector-1', [
      { toolId: 'second', activationStatus: 'disabled', invocationMode: 'ask', expectedPolicyRevision: 0 },
      { toolId: 'first', activationStatus: 'enabled' }
    ]);
    expect(result.tools).toEqual([
      { tool_id: 'second', activation_status: 'disabled', invocation_mode: 'ask', policy_revision: 1 },
      { tool_id: 'first', activation_status: 'enabled', invocation_mode: 'direct', policy_revision: 0 }
    ]);
    expect((await api.listTools('connector-1')).tools[0].activation_status).toBe('enabled');
    expect((await api.listActivations('connector-1')).tools[1]).toEqual(result.tools[0]);
  });

  test('rejects stale policy revisions atomically', async () => {
    const api = activationApi();
    await api.saveActivations('connector-1', [{ toolId: 'second', invocationMode: 'ask', expectedPolicyRevision: 0 }]);
    await expect(api.saveActivations('connector-1', [
      { toolId: 'first', activationStatus: 'enabled' },
      { toolId: 'second', activationStatus: 'disabled', invocationMode: 'direct', expectedPolicyRevision: 0 }
    ])).rejects.toEqual(new HttpError(409, 'Conflict', {
      code: 'invocation_policy_revision_conflict',
      conflicts: [{ tool_id: 'second', expected_revision: 0, current_mode: 'ask', current_revision: 1 }]
    }));
    expect((await api.listActivations('connector-1')).tools).toEqual([
      { tool_id: 'first', activation_status: 'disabled', invocation_mode: 'direct', policy_revision: 0 },
      { tool_id: 'second', activation_status: 'enabled', invocation_mode: 'ask', policy_revision: 1 }
    ]);
  });

  test('rejects unknown tools before conflicts and mutations', async () => {
    const api = activationApi();
    await expect(api.saveActivations('connector-1', [
      { toolId: 'first', activationStatus: 'enabled', invocationMode: 'ask', expectedPolicyRevision: 9 },
      { toolId: 'unknown', activationStatus: 'enabled' }
    ])).rejects.toEqual(new HttpError(404, 'Not Found', { detail: 'Connector tool was not found' }));
    expect((await api.listActivations('connector-1')).tools[0]).toEqual({
      tool_id: 'first', activation_status: 'disabled', invocation_mode: 'direct', policy_revision: 0
    });
  });

  test('does not increment policy revisions for no-op updates', async () => {
    const api = activationApi();
    const initial = await api.saveActivations('connector-1', [{ toolId: 'first', invocationMode: 'direct', expectedPolicyRevision: 0 }]);
    const repeated = await api.saveActivations('connector-1', [{ toolId: 'first', invocationMode: 'direct', expectedPolicyRevision: 0 }]);
    expect(initial.tools[0].policy_revision).toBe(0);
    expect(repeated.tools[0].policy_revision).toBe(0);
  });

  test('rejects unknown connector reads and saves without mutating seeded state', async () => {
    const api = activationApi();
    const notFound = new HttpError(404, 'Not Found', { detail: 'OpenAPI connector not found' });
    await expect(api.listActivations('unknown')).rejects.toEqual(notFound);
    await expect(api.saveActivations('unknown', [{ toolId: 'first', activationStatus: 'enabled' }])).rejects.toEqual(notFound);
    expect((await api.listActivations('connector-1')).tools[0]).toEqual({
      tool_id: 'first', activation_status: 'disabled', invocation_mode: 'direct', policy_revision: 0
    });
  });
});
