import { describe, expect, test, vi } from 'vitest';
import { AdminApi } from './infrastructure/admin-api';
import { InMemoryPublicConfigurationProvider } from './infrastructure/public-configuration';
import { browserTransport } from './infrastructure/transport';
import type { McpEndpointAccessResult, McpEndpointSetup, McpRegistryPage, McpRegistrySearch } from './mcp-endpoint-setup';

const endpoint = 'https://demo.example/mcp';
const registryPage: McpRegistryPage = {
  servers: [{
    name: 'example/demo', title: 'Demo', description: '', version: '1.2.3',
    endpoints: [{ url: endpoint, required_headers: ['Authorization'] }]
  }],
  next_cursor: 'another+page/='
};
const accessWithOAuth: McpEndpointAccessResult = {
  anonymous_initialization: { kind: 'anonymous_access_rejected', status_code: 401 },
  oauth: {
    kind: 'oauth_discovered',
    metadata: {
      kind: 'discovered', endpoint_url: endpoint, issuer_url: 'https://issuer.example',
      available_scopes: ['read'], scope_source: 'resource', automatic_registration: 'available',
      automatic_client: { kind: 'dynamic_public' }, token_endpoint_auth_methods: ['none']
    }
  }
};

function client(payload: unknown, status: number = 200): { setup: McpEndpointSetup; request: ReturnType<typeof vi.fn<typeof fetch>> } {
  const request = vi.fn<typeof fetch>(async (): Promise<Response> => Response.json(payload, { status }));
  const { mcpEndpointSetup: setup } = new AdminApi(browserTransport({
    fetch: request,
    configuration: new InMemoryPublicConfigurationProvider({ apiBaseUrl: '/api', mcpBaseUrl: '/mcp' })
  }));
  return { setup, request };
}

describe('MCP registry search', (): void => {
  test('encodes the search term and opaque cursor without sending a body', async (): Promise<void> => {
    const { setup, request } = client(registryPage);
    const query = { term: '  demo & tools  ', limit: 7, cursor: 'opaque+cursor/=' };
    expect(await setup.search(query)).toEqual(registryPage);
    expect(request).toHaveBeenCalledExactlyOnceWith(
      '/api/admin/connectors/mcp/registry/search?term=demo+%26+tools&limit=7&cursor=opaque%2Bcursor%2F%3D',
      expect.objectContaining({ method: 'GET' })
    );
    expect(request.mock.calls[0][1]?.body).toBeUndefined();
  });

  test('accepts a mixed page with an opaque percent-encoded endpoint path', async (): Promise<void> => {
    const page = { ...registryPage, servers: [...registryPage.servers, { ...registryPage.servers[0], name: 'example/encoded', endpoints: [{ url: `${endpoint}/%FF`, required_headers: [] }] }] };
    const { setup } = client(page);
    expect(await setup.search({ term: 'demo' })).toEqual(page);
  });

  test('leaves omitted pagination to server defaults and accepts an empty page', async (): Promise<void> => {
    const emptyPage = { servers: [], next_cursor: '' };
    const { setup, request } = client(emptyPage);
    expect(await setup.search({ term: 'demo' })).toEqual(emptyPage);
    expect(request.mock.calls[0][0]).toBe('/api/admin/connectors/mcp/registry/search?term=demo');
  });

  test.each<McpRegistrySearch>([
    { term: ' a ' }, { term: 'x'.repeat(257) }, { term: 'demo', limit: 0 },
    { term: 'demo', limit: 101 }, { term: 'demo', limit: 1.5 }, { term: 'demo', cursor: 'x'.repeat(2049) }
  ])('rejects an invalid registry query before sending it', async (query): Promise<void> => {
    const { setup, request } = client(registryPage);
    await expect(setup.search(query)).rejects.toMatchObject({ name: 'SchemaValidationError', direction: 'outbound' });
    expect(request).not.toHaveBeenCalled();
  });

  test.each([
    { ...registryPage, next_cursor: null },
    { ...registryPage, servers: [{ ...registryPage.servers[0], endpoints: [] }] },
    { ...registryPage, servers: [{ ...registryPage.servers[0], endpoints: [{ url: 'https://demo.example/{workspace}', required_headers: [] }] }] },
    { ...registryPage, servers: [{ ...registryPage.servers[0], endpoints: [{ url: endpoint, required_headers: [{ name: 'Authorization' }] }] }] }
  ])('rejects malformed registry pages', async (payload): Promise<void> => {
    const { setup } = client(payload);
    await expect(setup.search({ term: 'demo' })).rejects.toMatchObject({ name: 'SchemaValidationError', direction: 'inbound' });
  });

  test('keeps registry unavailability as a transport error', async (): Promise<void> => {
    const body = { detail: { code: 'mcp_registry_unavailable' } };
    const { setup, request } = client(body, 502);
    await expect(setup.search({ term: 'demo' })).rejects.toMatchObject({ name: 'HttpError', status: 502, body });
    expect(request).toHaveBeenCalledTimes(1);
  });
});

describe('MCP endpoint access check', (): void => {
  test.each<McpEndpointAccessResult>([
    accessWithOAuth,
    { anonymous_initialization: { kind: 'anonymous_initialization_succeeded' }, oauth: { kind: 'oauth_not_confirmed' } },
    { anonymous_initialization: { kind: 'inconclusive', reason: 'invalid_mcp_protocol' }, oauth: { kind: 'oauth_not_checked' } },
    {
      anonymous_initialization: { kind: 'anonymous_access_rejected', status_code: 403 },
      oauth: { kind: 'oauth_discovered', metadata: { kind: 'issuer_selection_required', endpoint_url: endpoint, issuer_urls: ['https://issuer.example', 'https://other.example'] } }
    }
  ])('posts just the endpoint URL and returns the access evidence', async (payload): Promise<void> => {
    const { setup, request } = client(payload);
    expect(await setup.checkAccess(endpoint)).toEqual(payload);
    expect(request).toHaveBeenCalledExactlyOnceWith('/api/admin/connectors/mcp/check-access', expect.objectContaining({
      method: 'POST', body: JSON.stringify({ endpoint_url: endpoint })
    }));
  });

  test.each(['http://demo.example/mcp', `${endpoint}?token=secret`, 'https://user:secret@demo.example/mcp'])(
    'rejects an invalid endpoint before sending it', async (url): Promise<void> => {
      const { setup, request } = client(accessWithOAuth);
      await expect(setup.checkAccess(url)).rejects.toMatchObject({ name: 'SchemaValidationError', direction: 'outbound' });
      expect(request).not.toHaveBeenCalled();
    }
  );

  test.each([
    { ...accessWithOAuth, anonymous_initialization: { kind: 'anonymous_access_rejected', status_code: 404 } },
    { ...accessWithOAuth, anonymous_initialization: { kind: 'inconclusive', reason: 'unknown_error' } },
    { ...accessWithOAuth, oauth: { kind: 'oauth_discovered', metadata: { kind: 'discovered', endpoint_url: endpoint } } },
    { ...accessWithOAuth, oauth: { kind: 'oauth_not_confirmed', raw_metadata: {} } },
    { ...accessWithOAuth, oauth: { kind: 'oauth_discovered', metadata: { kind: 'issuer_selection_required', endpoint_url: 'https://different.example/mcp', issuer_urls: ['https://issuer.example', 'https://other.example'] } } }
  ])('rejects malformed or mismatched access evidence', async (payload): Promise<void> => {
    const { setup } = client(payload);
    await expect(setup.checkAccess(endpoint)).rejects.toMatchObject({ name: 'SchemaValidationError', direction: 'inbound' });
  });
});
