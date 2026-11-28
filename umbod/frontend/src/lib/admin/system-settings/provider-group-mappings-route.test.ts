import { expect, test, vi } from 'vitest';
import { AdminApi } from '../infrastructure/admin-api';
import { InMemoryPublicConfigurationProvider } from '../infrastructure/public-configuration';
import { browserTransport, type Transport, type TransportRequest } from '../infrastructure/transport';
import type { ProviderGroupMappings, ProviderGroupMappingsPatch } from './domain/provider-group-mappings';

const path = '/admin/system-settings/provider-group-mappings';
const first = { external_value: ' Maintain\n\ufeff', group_id: 'team-a' };
const second = { ...first, group_id: 'team-b' };
const deployment: ProviderGroupMappings = { mappings: [first, second], source: 'deployment_default' };

class RecordingTransport implements Transport {
  readonly requests: TransportRequest<unknown>[] = [];

  constructor(private readonly response: ProviderGroupMappings) {}

  async request<T>(request: TransportRequest<T>): Promise<T> {
    this.requests.push(request);
    if (request.requestBody?.kind === 'json') request.requestBody.schema.parse(request.requestBody.value);
    if (!request.outputSchema) throw new Error('Missing response schema');
    return request.outputSchema.parse(this.response);
  }
}

test('uses the mappings resource with explicit replacements and reset, preserving order and literal values', async (): Promise<void> => {
  const transport = new RecordingTransport(deployment);
  const api = new AdminApi(transport).providerGroupMappings;
  const { signal } = new AbortController();
  const set: ProviderGroupMappingsPatch = { operation: 'set', mappings: [second, first] };
  const empty: ProviderGroupMappingsPatch = { operation: 'set', mappings: [] };
  const reset: ProviderGroupMappingsPatch = { operation: 'reset' };

  await expect(api.get(signal)).resolves.toEqual(deployment);
  await api.update(set, signal);
  await api.update(empty, signal);
  await expect(api.update(reset, signal)).resolves.toEqual(deployment);
  expect(transport.requests.map(({ method, path, signal, requestBody }) => [
    method, path, signal, requestBody?.kind === 'json' ? requestBody.schema.parse(requestBody.value) : undefined
  ])).toEqual([
    ['GET', path, signal, undefined],
    ['PATCH', path, signal, set],
    ['PATCH', path, signal, empty],
    ['PATCH', path, signal, reset]
  ]);
});

test.each(['admin_override', 'built_in_default', 'inherited_claim_default'] as const)('accepts mappings from %s', async (source): Promise<void> => {
  const result: ProviderGroupMappings = { mappings: source === 'built_in_default' ? [] : deployment.mappings, source };
  const api = new AdminApi(new RecordingTransport(result)).providerGroupMappings;
  await expect(api.get(new AbortController().signal)).resolves.toEqual(result);
});

test.each([
  { operation: 'reset', mappings: [] },
  { operation: 'set', mappings: [first, first] },
  { operation: 'set', mappings: [{ ...first, group_id: null }] },
  { operation: 'set', mappings: [{ external_value: first.external_value }] },
  { operation: 'set', mappings: [{ ...first, issuer: 'provider' }] },
  { operation: 'set', mappings: [{ ...first, claim: 'team.role' }] },
  { operation: 'set', mappings: [{ ...first, external_value: ' \u001c\u0085 ' }] },
  { operation: 'set', mappings: [{ ...first, group_id: '' }] }
])('rejects invalid operations before sending a request: %j', async (body): Promise<void> => {
  const fetch = vi.fn<typeof globalThis.fetch>();
  const api = new AdminApi(browserTransport({ fetch })).providerGroupMappings;
  await expect(api.update(body as ProviderGroupMappingsPatch, new AbortController().signal)).rejects.toMatchObject({ direction: 'outbound' });
  expect(fetch).not.toHaveBeenCalled();
});

test.each([
  { mappings: [], source: 'unknown_source' },
  { mappings: [first, first], source: 'admin_override' },
  { mappings: [{ ...first, group_id: null }], source: 'deployment_default' },
  { mappings: [{ ...first, external_value: 1 }], source: 'deployment_default' },
  { mappings: [{ ...first, issuer: 'provider', claim: 'team.role' }], source: 'deployment_default' }
])('rejects invalid responses: %j', async (response): Promise<void> => {
  const fetch = vi.fn<typeof globalThis.fetch>().mockResolvedValue(Response.json(response));
  const configuration = new InMemoryPublicConfigurationProvider({ apiBaseUrl: '/api', mcpBaseUrl: '/mcp' });
  const api = new AdminApi(browserTransport({ fetch, configuration })).providerGroupMappings;
  await expect(api.get(new AbortController().signal)).rejects.toMatchObject({ direction: 'inbound' });
});
