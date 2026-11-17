import { describe, expect, test, vi } from 'vitest';
import { AdminApi } from '../infrastructure/admin-api';
import { browserTransport } from '../infrastructure/transport';
import { InMemoryPublicConfigurationProvider } from '../infrastructure/public-configuration';
import { EndpointResourceMismatchError, endpointDiscoveryRequestSchema, endpointDiscoveryResultSchema, type EndpointDiscoveryRequest, type EndpointDiscoveryResult } from './domain/discovery';
import { clientRequestSchema, clientResponseSchema } from './domain/schemas';
import { InMemoryPersonalServerDiscovery } from './discovery.test-support';
import { InMemoryPersonalServers } from './in-memory';
import { createFixture } from './fixtures.test-support';

const automaticRequest: EndpointDiscoveryRequest = { endpoint_url: 'https://provider.test/mcp', issuer_selection: { kind: 'automatic' } };
const selectedRequest: EndpointDiscoveryRequest = { ...automaticRequest, issuer_selection: { kind: 'selected', issuer_url: 'https://issuer.test' } };
const discovered: EndpointDiscoveryResult = { kind: 'discovered', endpoint_url: automaticRequest.endpoint_url, issuer_url: 'https://issuer.test', available_scopes: ['records:read'], scope_source: 'resource', automatic_registration: 'available', token_endpoint_auth_methods: ['none', 'client_secret_basic'] };
const selectionRequired: EndpointDiscoveryResult = { kind: 'issuer_selection_required', endpoint_url: automaticRequest.endpoint_url, issuer_urls: ['https://issuer.test', 'https://other.test'] };

function harness(response: unknown = discovered): { api: AdminApi; request: ReturnType<typeof vi.fn<typeof fetch>> } {
  const request = vi.fn<typeof fetch>(async (): Promise<Response> => Response.json(response));
  const api = new AdminApi(browserTransport({ fetch: request, configuration: new InMemoryPublicConfigurationProvider({ apiBaseUrl: '/api', mcpBaseUrl: '/mcp' }) }));
  return { api, request };
}

describe('unsaved personal endpoint discovery', (): void => {
  test.each([discovered, selectionRequired])('posts the unsaved endpoint without a saved setup receipt', async (result): Promise<void> => {
    const { api, request } = harness(result);
    expect(await api.personalServerDiscovery.discover(automaticRequest)).toEqual(result);
    expect(request).toHaveBeenCalledTimes(1);
    expect(request.mock.calls[0][0]).toBe('/api/admin/connectors/mcp/personal-oauth/discovery');
    expect(request.mock.calls[0][1]).toMatchObject({ method: 'POST', body: JSON.stringify(automaticRequest) });
  });

  test('sends and fences the explicitly selected issuer', async (): Promise<void> => {
    const { api, request } = harness();
    expect(await api.personalServerDiscovery.discover(selectedRequest)).toEqual(discovered);
    expect(request.mock.calls[0][1]?.body).toBe(JSON.stringify(selectedRequest));
    const mismatch = harness({ ...discovered, issuer_url: 'https://other.test' });
    await expect(mismatch.api.personalServerDiscovery.discover(selectedRequest)).rejects.toMatchObject({ direction: 'inbound' });
  });

  test('validates outbound inputs before network', async (): Promise<void> => {
    const { api, request } = harness();
    await expect(api.personalServerDiscovery.discover({ ...automaticRequest, endpoint_url: 'http://provider.test' })).rejects.toMatchObject({ direction: 'outbound' });
    expect(request).not.toHaveBeenCalled();
  });

  test.each([
    { ...automaticRequest, endpoint_url: 'https://provider.test/mcp?workspace=example' },
    { ...automaticRequest, endpoint_url: 'https://user:secret@provider.test/mcp' },
    { ...automaticRequest, expected_revision: 'saved' },
    { ...automaticRequest, issuer_selection: { kind: 'automatic', issuer_url: 'https://issuer.test' } },
    { ...automaticRequest, issuer_selection: { kind: 'selected', issuer_url: 'http://issuer.test' } },
    { ...automaticRequest, issuer_selection: { kind: 'selected', issuer_url: 'https://issuer.test/#fragment' } },
    { ...automaticRequest, client_secret: 'secret' }
  ])('rejects unexpected request fields and unsafe issuer selection', (request): void => {
    expect(endpointDiscoveryRequestSchema.safeParse(request).success).toBe(false);
  });

  test.each([
    { ...discovered, endpoint_url: 'https://other.test/mcp' },
    { ...selectionRequired, endpoint_url: 'https://other.test/mcp' },
    { ...discovered, client_secret: 'secret' },
    { ...discovered, raw_metadata: { authorization_endpoint: 'https://issuer.test' } },
    { ...discovered, token_endpoint_auth_methods: [''] },
    { ...discovered, token_endpoint_auth_methods: ['x'.repeat(129)] },
    { ...discovered, token_endpoint_auth_methods: Array(17).fill('none') },
    { ...discovered, available_scopes: ['read', 'read'] },
    { ...discovered, scope_source: 'registration' },
    { ...discovered, automatic_registration: true },
    { ...selectionRequired, issuer_urls: ['https://issuer.test'] },
    { ...selectionRequired, issuer_urls: ['https://issuer.test', 'https://issuer.test'] },
    { ...selectionRequired, issuer_urls: ['https://issuer.test', 'http://other.test'] },
    { ...selectionRequired, issuer_urls: Array.from({ length: 17 }, (_, index): string => `https://issuer${index}.test`) },
    { ...selectionRequired, raw_metadata: {} }
  ])('rejects untrusted metadata and mismatched endpoint identity', async (response): Promise<void> => {
    const { api } = harness(response);
    await expect(api.personalServerDiscovery.discover(automaticRequest)).rejects.toMatchObject({ direction: 'inbound' });
  });

  test('preserves issuer strings exactly and accepts sixteen unique issuers', (): void => {
    const result = { ...selectionRequired, issuer_urls: Array.from({ length: 16 }, (_, index): string => `https://issuer${index}.test/path/`) };
    expect(endpointDiscoveryResultSchema.parse(result)).toEqual(result);
  });

  test('maps the validated resource mismatch into a safe domain failure without retrying', async (): Promise<void> => {
    const { api, request } = harness();
    request.mockResolvedValueOnce(Response.json({ detail: { code: 'personal_oauth_discovery_failed', stage: 'discovery', reason: 'resource_mismatch' } }, { status: 422 }));
    await expect(api.personalServerDiscovery.discover(automaticRequest)).rejects.toBeInstanceOf(EndpointResourceMismatchError);
    expect(request).toHaveBeenCalledTimes(1);
  });

  test.each([
    { detail: { code: 'unrelated', stage: 'discovery', reason: 'resource_mismatch' } },
    { detail: { code: 'personal_oauth_discovery_failed', stage: 'registration', reason: 'resource_mismatch' } },
    { detail: { code: 'personal_oauth_discovery_failed', stage: 'discovery', reason: 'network_failure' } },
    { detail: { code: 'personal_oauth_discovery_failed', stage: 'discovery', reason: 'resource_mismatch', raw_metadata: 'private' } },
    { detail: 'resource_mismatch' },
    null
  ])('does not reinterpret unrelated or malformed HTTP errors', async (body): Promise<void> => {
    const { api, request } = harness();
    request.mockResolvedValueOnce(Response.json(body, { status: 422 }));
    await expect(api.personalServerDiscovery.discover(automaticRequest)).rejects.toMatchObject({ name: 'HttpError', status: 422 });
  });

  test.each([401, 403, 500])('preserves status %s even with a mismatch-shaped body', async (status): Promise<void> => {
    const { api, request } = harness();
    request.mockResolvedValueOnce(Response.json({ detail: { code: 'personal_oauth_discovery_failed', stage: 'discovery', reason: 'resource_mismatch' } }, { status }));
    await expect(api.personalServerDiscovery.discover(automaticRequest)).rejects.toMatchObject({ name: status === 401 ? 'AuthenticationRequiredError' : 'HttpError' });
  });

  test('leaves HTTP and network failures to the transport without retries', async (): Promise<void> => {
    const { api, request } = harness();
    request.mockResolvedValueOnce(Response.json({ detail: 'unavailable' }, { status: 422 }));
    await expect(api.personalServerDiscovery.discover(automaticRequest)).rejects.toMatchObject({ status: 422 });
    request.mockRejectedValueOnce(new Error('network unavailable'));
    await expect(api.personalServerDiscovery.discover(automaticRequest)).rejects.toMatchObject({ name: 'NetworkError' });
    expect(request).toHaveBeenCalledTimes(2);
  });

  test('in-memory discovery validates, records requests and consumes only seeded results', async (): Promise<void> => {
    const discovery = new InMemoryPersonalServerDiscovery([selectionRequired, discovered]);
    expect(await discovery.discover(automaticRequest)).toEqual(selectionRequired);
    expect(await discovery.discover(selectedRequest)).toEqual(discovered);
    expect(discovery.requests).toEqual([automaticRequest, selectedRequest]);
    await expect(discovery.discover(automaticRequest)).rejects.toThrow('No endpoint discovery result queued');
  });

  test('in-memory discovery rejects invalid seeded metadata', (): void => {
    expect((): InMemoryPersonalServerDiscovery => new InMemoryPersonalServerDiscovery([{ ...discovered, endpoint_url: 'http://provider.test' }])).toThrow();
    const unsafeResult = { ...discovered, client_secret: 'secret' };
    expect((): InMemoryPersonalServerDiscovery => new InMemoryPersonalServerDiscovery([unsafeResult])).toThrow();
  });

  test('in-memory discovery enforces endpoint and selected issuer identities', async (): Promise<void> => {
    await expect(new InMemoryPersonalServerDiscovery([discovered]).discover({ ...automaticRequest, endpoint_url: 'https://different.test' })).rejects.toThrow();
    await expect(new InMemoryPersonalServerDiscovery([discovered]).discover({ ...automaticRequest, issuer_selection: { kind: 'selected', issuer_url: 'https://different.test' } })).rejects.toThrow();
    const discovery = new InMemoryPersonalServerDiscovery([discovered]);
    await expect(discovery.discover({ ...automaticRequest, endpoint_url: 'invalid' })).rejects.toThrow();
    expect(discovery.requests).toEqual([]);
    expect(await discovery.discover(automaticRequest)).toEqual(discovered);
  });
});

describe('durable dynamic issuer approval', (): void => {
  test('keeps absent legacy approval absent and validates bounded HTTPS approval', (): void => {
    for (const schema of [clientRequestSchema, clientResponseSchema]) {
      expect(schema.parse({ kind: 'dynamic_public' })).toEqual({ kind: 'dynamic_public' });
      expect(schema.parse({ kind: 'dynamic_public', approved_issuers: ['https://issuer.test'] })).toEqual({ kind: 'dynamic_public', approved_issuers: ['https://issuer.test'] });
      expect(schema.safeParse({ kind: 'dynamic_public', approved_issuers: ['https://issuer.test', 'https://other.test'] }).success).toBe(false);
      expect(schema.safeParse({ kind: 'dynamic_public', approved_issuers: ['http://issuer.test'] }).success).toBe(false);
      expect(schema.safeParse({ kind: 'dynamic_public', approved_issuers: null }).success).toBe(false);
    }
  });

  test('roundtrips approval through in-memory creation and policy replacement', async (): Promise<void> => {
    const servers = new InMemoryPersonalServers();
    const input = createFixture();
    input.configuration.oauth_configuration.client = { kind: 'dynamic_public', approved_issuers: ['https://issuer.test'] };
    const server = await servers.create(input);
    const policy = await servers.policy(server.connector_id);
    expect(policy.client).toEqual(input.configuration.oauth_configuration.client);
    const settings = { requested_scopes: [], client: { kind: 'dynamic_public' as const, approved_issuers: ['https://other.test'] } };
    expect((await servers.replacePolicy(server.connector_id, { expected_revision: policy.revision, settings })).client).toEqual(settings.client);
    expect((await servers.policy(server.connector_id)).client).toEqual(settings.client);
  });
});
