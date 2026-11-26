import { expect, test, vi } from 'vitest';
import { AdminApi } from '../infrastructure/admin-api';
import { InMemoryPublicConfigurationProvider } from '../infrastructure/public-configuration';
import { browserTransport, type Transport, type TransportRequest } from '../infrastructure/transport';
import type { FilesystemSettingsPatch } from './domain/filesystem-settings';

const path = '/admin/system-settings/filesystem';
const effective = { require_mcp_file_deletion_approval: { value: false, source: 'deployment_default' } };

class RecordingTransport implements Transport {
  readonly requests: TransportRequest<unknown>[] = [];

  async request<T>(request: TransportRequest<T>): Promise<T> {
    this.requests.push(request);
    if (request.requestBody?.kind === 'json') request.requestBody.schema.parse(request.requestBody.value);
    if (!request.outputSchema) throw new Error('Missing response schema');
    return request.outputSchema.parse(effective);
  }
}

test('gets effective settings and sends explicit set and reset operations', async (): Promise<void> => {
  const transport = new RecordingTransport();
  const api = new AdminApi(transport).filesystemSettings;
  const { signal } = new AbortController();
  const set = { require_mcp_file_deletion_approval: { operation: 'set', value: false } } as const;
  const reset = { require_mcp_file_deletion_approval: { operation: 'reset' } } as const;
  await expect(api.get(signal)).resolves.toEqual(effective);
  await api.update(set, signal);
  await expect(api.update(reset, signal)).resolves.toEqual(effective);
  expect(transport.requests.map(({ method, path, signal, requestBody }) => [
    method, path, signal, requestBody?.kind === 'json' ? requestBody.value : undefined
  ])).toEqual([
    ['GET', path, signal, undefined],
    ['PATCH', path, signal, set],
    ['PATCH', path, signal, reset]
  ]);
});

test.each([
  { operation: 'set', value: 'false' },
  { operation: 'reset', value: false },
  { operation: 'set' }
])('rejects invalid PATCH operations before contacting the API: %j', async (operation): Promise<void> => {
  const fetch = vi.fn<typeof globalThis.fetch>();
  const api = new AdminApi(browserTransport({ fetch })).filesystemSettings;
  const invalid = { require_mcp_file_deletion_approval: operation } as FilesystemSettingsPatch;
  await expect(api.update(invalid, new AbortController().signal)).rejects.toMatchObject({ direction: 'outbound' });
  expect(fetch).not.toHaveBeenCalled();
});

test.each([
  { value: false, source: 'unknown' },
  { value: 'false', source: 'deployment_default' },
  { value: false, source: 'deployment_default', extra: true }
])('rejects unrecognized response shapes: %j', async (approval): Promise<void> => {
  const fetch = vi.fn<typeof globalThis.fetch>().mockResolvedValue(Response.json({ require_mcp_file_deletion_approval: approval }));
  const configuration = new InMemoryPublicConfigurationProvider({ apiBaseUrl: '/api', mcpBaseUrl: '/mcp' });
  const api = new AdminApi(browserTransport({ fetch, configuration })).filesystemSettings;
  await expect(api.get(new AbortController().signal)).rejects.toMatchObject({ direction: 'inbound' });
});
