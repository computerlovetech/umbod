import { describe, expect, test, vi } from 'vitest';
import { AdminApi } from '../infrastructure/admin-api';
import { browserTransport, SchemaValidationError } from '../infrastructure/transport';
import { InMemoryPublicConfigurationProvider } from '../infrastructure/public-configuration';
import type { PersonalServerAdministration } from './administration';
import { createFixture, policyFixture, serverFixture, summaryFixture } from './fixtures.test-support';
import type { PersonalSettings } from './domain/schemas';

function harness(response: (path: string, init: RequestInit) => unknown): { api: AdminApi; request: ReturnType<typeof vi.fn<typeof fetch>> } {
  const request = vi.fn<typeof fetch>(async (input, init) => {
    const body = response(String(input), init ?? {});
    return body === undefined ? new Response(null, { status: 204 }) : Response.json(body, { status: init?.method === 'POST' ? 201 : 200 });
  });
  return { api: new AdminApi(browserTransport({ fetch: request, configuration: new InMemoryPublicConfigurationProvider({ apiBaseUrl: '/api', mcpBaseUrl: '/mcp' }) })), request };
}

describe('personal server HTTP port contract', () => {
  test('composes filtered strict list, selected definition and policy with API base once', async () => {
    const { api, request } = harness((path) => path.endsWith('/personal-oauth') ? policyFixture() : path.endsWith('/mcp') ? { connectors: [summaryFixture(), { ...summaryFixture('shared'), authorization_mode: 'shared', auth_mode: 'none' }] } : serverFixture());
    const port: PersonalServerAdministration = api.personalServers;
    expect(await port.list()).toEqual([summaryFixture()]);
    expect(await port.get('personal')).toEqual(serverFixture());
    expect(await port.policy('personal')).toEqual(policyFixture());
    expect(request.mock.calls.every(([path]) => String(path).startsWith('/api/admin/'))).toBe(true);
    expect(request.mock.calls.some(([path]) => String(path).includes('/api/api'))).toBe(false);
  });
  test.each<PersonalSettings['client']>([
    { kind: 'dynamic_public' },
    { kind: 'preconfigured_public', issuer_url: 'https://Issuer.test:443/Exact/', client_id: 'public' },
    { kind: 'preconfigured_confidential', issuer_url: 'https://issuer.test', client_id: 'id', token_endpoint_auth_method: 'client_secret_basic', client_secret: 'fresh-secret' },
    { kind: 'preconfigured_confidential', issuer_url: 'https://issuer.test', client_id: 'id', token_endpoint_auth_method: 'client_secret_post', client_secret: 'fresh-secret' }
  ])('creates only through dedicated personal route with exact $kind settings', async (client) => {
    const { api, request } = harness(() => serverFixture());
    const input = createFixture();
    input.configuration.oauth_configuration = { requested_scopes: ['z', 'A'], client };
    await api.personalServers.create(input);
    expect(request).toHaveBeenCalledTimes(1);
    const [path, init] = request.mock.calls[0];
    expect(path).toBe('/api/admin/connectors/mcp/personal-oauth');
    expect(init?.method).toBe('POST');
    expect(JSON.parse(String(init?.body))).toEqual({ ...input, configuration: { ...input.configuration, oauth_configuration: { requested_scopes: ['A', 'z'], client } } });
  });
  test('sends complete revision-checked replacement and exact bodyless publication and deletion', async () => {
    const { api, request } = harness((path, init) => {
      if (path.endsWith('/personal-oauth')) return { ...policyFixture('a b'), revision: 'r2' };
      if (path.endsWith('/publication')) return { connector_id: 'a b', publication_status: init.method === 'PUT' ? 'published' : 'unpublished' };
      if (init.method === 'DELETE') return undefined;
      return { ...serverFixture(), connector_id: 'a b' };
    });
    await api.personalServers.replacePolicy('a b', { expected_revision: 'r1', settings: { requested_scopes: ['read'], client: { kind: 'dynamic_public' } } });
    await api.personalServers.publish('a b');
    await api.personalServers.withdraw('a b');
    await api.personalServers.delete('a b');
    const writes = request.mock.calls.filter(([, init]) => init?.method !== 'GET');
    expect(writes.map(([path, init]) => [init?.method, path])).toEqual([
      ['PUT', '/api/admin/connectors/mcp/a%20b/personal-oauth'], ['PUT', '/api/admin/connectors/mcp/a%20b/publication'], ['DELETE', '/api/admin/connectors/mcp/a%20b/publication'], ['DELETE', '/api/admin/connectors/mcp/a%20b']
    ]);
    expect(JSON.parse(String(writes[0][1]?.body))).toEqual({ expected_revision: 'r1', settings: { requested_scopes: ['read'], client: { kind: 'dynamic_public' } } });
    for (const [, init] of writes.slice(1)) {
      expect(init?.body).toBeUndefined();
      expect(init?.headers).not.toHaveProperty('Content-Type');
    }
  });
  test.each(['https://user:secret@provider.test/mcp', 'https://@provider.test/mcp', 'https://provider.test/mcp#fragment', 'https://provider.test:0/mcp'])('invalid endpoint %s fails before network', async (endpoint) => {
    const { api, request } = harness(() => serverFixture());
    const input = createFixture();
    input.configuration.endpoint_url = endpoint;
    await expect(api.personalServers.create(input)).rejects.toMatchObject({ direction: 'outbound' });
    expect(request).not.toHaveBeenCalled();
  });
  test('invalid create bodies and confidential omission fail before network', async () => {
    const { api, request } = harness(() => serverFixture());
    const input = createFixture();
    input.configuration.oauth_configuration.requested_scopes = ['read', 'read'];
    await expect(api.personalServers.create(input)).rejects.toMatchObject({ direction: 'outbound' });
    await expect(api.personalServers.replacePolicy('personal', { expected_revision: 'r1', settings: { requested_scopes: [], client: { kind: 'preconfigured_confidential', issuer_url: 'https://issuer.test', client_id: 'id', token_endpoint_auth_method: 'client_secret_basic' } } } as never)).rejects.toThrow();
    expect(request).not.toHaveBeenCalled();
  });
  test.each(['policy', 'replacePolicy', 'publish', 'withdraw', 'delete'] as const)('guards personal ownership before %s', async (operation) => {
    const { api, request } = harness(() => ({ ...serverFixture(), authorization_mode: 'shared' }));
    const result = operation === 'replacePolicy' ? api.personalServers.replacePolicy('personal', { expected_revision: 'r1', settings: { requested_scopes: [], client: { kind: 'dynamic_public' } } }) : api.personalServers[operation]('personal');
    await expect(result).rejects.toBeInstanceOf(SchemaValidationError);
    expect(request).toHaveBeenCalledTimes(1);
    expect(request.mock.calls[0][1]?.method).toBe('GET');
  });
  test('rejects response plaintext, masking placeholders and malformed ownership', async () => {
    const { api } = harness((path) => path.endsWith('/personal-oauth') ? { ...policyFixture(), client: { kind: 'preconfigured_confidential', issuer_url: 'https://issuer.test', client_id: 'id', token_endpoint_auth_method: 'client_secret_basic', client_secret_configured: true, client_secret: '********' } } : serverFixture());
    await expect(api.personalServers.policy('personal')).rejects.toMatchObject({ direction: 'inbound' });
    const { authorization_mode, ...missingOwnership } = summaryFixture();
    const malformed = harness(() => ({ connectors: [missingOwnership] }));
    await expect(malformed.api.personalServers.list()).rejects.toMatchObject({ direction: 'inbound' });
    await expect(malformed.api.downstreamMcpConnectors.list()).rejects.toMatchObject({ direction: 'inbound' });
  });
  test('shared list excludes personal rows and every shared command guards ownership first', async () => {
    const { api, request } = harness((path) => path.endsWith('/mcp') ? { connectors: [summaryFixture()] } : serverFixture());
    expect(await api.downstreamMcpConnectors.list()).toEqual({ connectors: [] });
    const shared = api.downstreamMcpConnectors;
    const operations = [() => shared.get('personal'), () => shared.tools('personal'), () => shared.prompts('personal'), () => shared.resources('personal'), () => shared.discover('personal'), () => shared.listActivations('personal'), () => shared.publish('personal'), () => shared.unpublish('personal'), () => shared.delete('personal'), () => shared.putConfiguration('personal', { endpoint_url: 'https://p.test', auth_mode: 'none', bearer_token: null }), () => shared.patchMetadata('personal', { display_name: 'Name' })];
    for (const operation of operations) await expect(operation()).rejects.toMatchObject({ direction: 'inbound' });
    expect(request.mock.calls.every(([, init]) => init?.method === 'GET')).toBe(true);
    expect(request.mock.calls.slice(1).every(([path]) => String(path).endsWith('/mcp/personal'))).toBe(true);
  });
});
