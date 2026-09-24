import { describe, expect, test, vi } from 'vitest';
import { serverTransport, type Transport, type TransportRequest } from './infrastructure/transport';
import { connectorApiResponseSchema, connectorDetailApiResponseSchema } from './connectors';
import {
  checkConnectorConfiguration,
  ConnectorsApi,
  loadConnectorList,
  publishConnector,
  saveConnectorConfiguration,
  saveToolActivations
} from './connectors-api';

function recordingTransport(): { transport: Transport; calls: TransportRequest<unknown>[] } {
  const calls: TransportRequest<unknown>[] = [];
  const transport: Transport = {
    async request(opts) {
      calls.push(opts as TransportRequest<unknown>);
      return undefined as never;
    }
  };
  return { transport, calls };
}

function apiFromFetch(fetch: ReturnType<typeof vi.fn>): ConnectorsApi {
  return new ConnectorsApi(serverTransport(fetch as unknown as typeof globalThis.fetch));
}

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
    ...init
  });
}

describe('connector list and detail schemas', () => {
  test('parse distinct strict contracts and retain detail tools', () => {
    const summary = {
      id: 'test', display_name: 'Test', description: 'Test connector', extension: { source: 'built-in' },
      publication_status: 'draft', available_actions: ['publish']
    };
    const detail = {
      id: 'test', display_name: 'Test', description: 'Test connector', capability_description: 'Echo messages',
      base_capability_description: 'Echo messages', effective_capability_description: 'Echo messages safely',
      capability_description_override: { state: 'overridden', revision: 2 },
      extension: { source: 'built-in', package: null }, publication_status: 'draft', tools: [{
        operation_name: 'echo', label: 'Echo', description: 'Echo input',
        parameters: { type: 'object', properties: {}, required: [] }, output_schema_status: 'absent'
      }]
    };
    expect(connectorApiResponseSchema.parse({ connectors: [summary] }).connectors[0]).toEqual(summary);
    expect(connectorApiResponseSchema.safeParse({ connectors: [detail] }).success).toBe(false);
    expect(connectorDetailApiResponseSchema.parse(detail)).toEqual(detail);
    expect(connectorDetailApiResponseSchema.safeParse({ ...detail, tools: [{ ...detail.tools[0], unexpected: true }] }).success).toBe(false);
  });

  test('rejects malformed summaries without guaranteed publication fields', () => {
    const summary = { id: 'test', display_name: 'Test', description: 'Test connector', extension: { source: 'built-in' } };
    expect(connectorApiResponseSchema.safeParse({ connectors: [summary] }).success).toBe(false);
  });
});

describe('ConnectorsApi route contracts', () => {
  test('connectors.list GETs the connectors collection with an output schema', () => {
    const { transport, calls } = recordingTransport();
    new ConnectorsApi(transport).connectors.list();

    expect(calls[0]).toMatchObject({ method: 'GET', path: '/admin/connectors/catalog' });
    expect(calls[0].outputSchema).toBeDefined();
  });

  test('connectors.get encodes the connector id in the path', () => {
    const { transport, calls } = recordingTransport();
    new ConnectorsApi(transport).connectors.get('a b');

    expect(calls[0]).toMatchObject({ method: 'GET', path: '/admin/connectors/catalog/a%20b' });
  });

  test('connectors.checkConfiguration POSTs with input and output validation', () => {
    const { transport, calls } = recordingTransport();
    new ConnectorsApi(transport).connectors.checkConfiguration('c1', { configuration: { token: 'x' } });

    expect(calls[0]).toMatchObject({
      method: 'POST',
      path: '/admin/connectors/catalog/c1/configuration/validations',
      body: { configuration: { token: 'x' } }
    });
    expect(calls[0].inputSchema).toBeDefined();
    expect(calls[0].outputSchema).toBeDefined();
  });

  test('connectors.saveConfiguration PUTs with both input and output validation', () => {
    const { transport, calls } = recordingTransport();
    new ConnectorsApi(transport).connectors.saveConfiguration('c1', { configuration: { token: 'x' } });

    expect(calls[0]).toMatchObject({
      method: 'PUT',
      path: '/admin/connectors/catalog/c1/configuration',
      body: { configuration: { token: 'x' } }
    });
    expect(calls[0].inputSchema).toBeDefined();
  });

  test('connectors.publish and unpublish target the publication resource', () => {
    const { transport, calls } = recordingTransport();
    const api = new ConnectorsApi(transport);
    api.connectors.publish('c1');
    api.connectors.unpublish('c1');

    expect(calls[0]).toMatchObject({ method: 'PUT', path: '/admin/connectors/catalog/c1/publication' });
    expect(calls[1]).toMatchObject({ method: 'DELETE', path: '/admin/connectors/catalog/c1/publication' });
  });

  test('tools.saveActivations PUTs the activation collection with input and output schemas', () => {
    const { transport, calls } = recordingTransport();
    new ConnectorsApi(transport).tools.saveActivations('c1', [
      { toolId: 'op.run', activationStatus: 'enabled', invocationMode: 'ask', expectedPolicyRevision: 2 },
      { toolId: 'op.read', invocationMode: 'direct', expectedPolicyRevision: 0 }
    ]);

    expect(calls).toHaveLength(1);
    expect(calls[0]).toMatchObject({
      method: 'PUT',
      path: '/admin/connectors/catalog/c1/tools/activation',
      body: { tools: [
        { tool_id: 'op.run', activation_status: 'enabled', invocation_mode: 'ask', expected_policy_revision: 2 },
        { tool_id: 'op.read', invocation_mode: 'direct', expected_policy_revision: 0 }
      ] }
    });
    expect(calls[0].path).not.toContain('invocation-policy');
    expect(calls[0].inputSchema).toBeDefined();
    expect(calls[0].outputSchema).toBeDefined();
  });
});

describe('loadConnectorList', () => {
  test('returns failure page data when the collection request fails', async () => {
    const fetch = vi.fn(async () => new Response('', { status: 500, statusText: 'Server Error' }));
    const data = await loadConnectorList(apiFromFetch(fetch), null);

    expect(data).toMatchObject({ status: 'failed', message: 'Failed to get connectors' });
  });

  test('returns empty page data when no connectors are available', async () => {
    const fetch = vi.fn(async () => jsonResponse({ connectors: [] }));
    const data = await loadConnectorList(apiFromFetch(fetch), null);

    expect(data).toMatchObject({ status: 'empty', connectors: [] });
  });

  test('loads summaries with only one collection request', async () => {
    const summary = { id: 'test', display_name: 'Test', description: 'Test connector', extension: { source: 'built-in' }, publication_status: 'draft', available_actions: ['publish'] };
    const fetch = vi.fn(async () => jsonResponse({ connectors: [summary] }));

    const data = await loadConnectorList(apiFromFetch(fetch), null);

    expect(data).toMatchObject({ status: 'ready', connectors: [{ id: 'test', tools: [] }] });
    expect(fetch).toHaveBeenCalledOnce();
  });
});

describe('publishConnector', () => {
  test('returns published with a success message on success', async () => {
    const fetch = vi.fn(async () => jsonResponse({}));
    const result = await publishConnector(apiFromFetch(fetch), 'c1');

    expect(result).toEqual({ status: 'published', successMessage: 'c1 was published successfully' });
  });

  test('surfaces the API message on failure', async () => {
    const fetch = vi.fn(async () => jsonResponse({ message: 'already published' }, { status: 409, statusText: 'Conflict' }));
    const result = await publishConnector(apiFromFetch(fetch), 'c1');

    expect(result).toEqual({ status: 'failed', errorMessage: 'already published' });
  });
});

describe('saveToolActivations', () => {
  test('sends all desired states in one batch request', async () => {
    const fetch = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => jsonResponse({
      connector_id: 'c1',
      tools: [
        { tool_id: 'first', activation_status: 'enabled', invocation_mode: 'ask', policy_revision: 1 },
        { tool_id: 'second', activation_status: 'disabled', invocation_mode: 'direct', policy_revision: 0 }
      ]
    }));
    const result = await saveToolActivations(apiFromFetch(fetch), {
      connectorId: 'c1',
      activations: [
        { operationName: 'first', activationStatus: 'enabled' },
        { operationName: 'second', activationStatus: 'disabled' }
      ]
    });

    expect(result).toEqual({ status: 'saved', connectorId: 'c1' });
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch.mock.calls[0][0]).toContain('/admin/connectors/catalog/c1/tools/activation');
    expect(JSON.parse(String(fetch.mock.calls[0][1]?.body))).toEqual({
      tools: [
        { tool_id: 'first', activation_status: 'enabled' },
        { tool_id: 'second', activation_status: 'disabled' }
      ]
    });
    expect(fetch.mock.calls[0][0]).not.toContain('invocation-policy');
  });
});

describe('checkConnectorConfiguration', () => {
  test('returns valid when the connector check passes', async () => {
    const fetch = vi.fn(async () => jsonResponse({ valid: true, message: null, field_messages: {} }));
    const result = await checkConnectorConfiguration(apiFromFetch(fetch), 'c1', { token: 'x' });

    expect(result).toEqual({ status: 'valid' });
  });

  test('returns invalid with messages when the connector check fails', async () => {
    const fetch = vi.fn(async () =>
      jsonResponse({ valid: false, message: 'Token rejected', field_messages: { token: 'Use a valid token' } })
    );
    const result = await checkConnectorConfiguration(apiFromFetch(fetch), 'c1', { token: 'bad' });

    expect(result).toEqual({ status: 'invalid', message: 'Token rejected', fieldMessages: { token: 'Use a valid token' } });
  });

  test('maps validation detail bodies into a failed result', async () => {
    const fetch = vi.fn(async () =>
      jsonResponse({ detail: [{ loc: ['body', 'token'], msg: 'field required' }] }, { status: 422, statusText: 'Unprocessable Entity' })
    );
    const result = await checkConnectorConfiguration(apiFromFetch(fetch), 'c1', { token: '' });

    expect(result).toEqual({ status: 'failed', errorMessage: 'token: field required' });
  });
});

describe('saveConnectorConfiguration', () => {
  test('returns saved on success', async () => {
    const fetch = vi.fn(async () => jsonResponse({}));
    const result = await saveConnectorConfiguration(apiFromFetch(fetch), 'c1', { token: 'x' });

    expect(result).toEqual({ status: 'saved' });
  });

  test('maps validation detail bodies into an error message', async () => {
    const fetch = vi.fn(async () =>
      jsonResponse({ detail: [{ loc: ['body', 'token'], msg: 'field required' }] }, { status: 400, statusText: 'Bad Request' })
    );
    const result = await saveConnectorConfiguration(apiFromFetch(fetch), 'c1', { token: '' });

    expect(result).toEqual({ status: 'failed', errorMessage: 'token: field required' });
  });
});
