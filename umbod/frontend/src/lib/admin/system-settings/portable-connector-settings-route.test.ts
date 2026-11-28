import { expect, test, vi } from 'vitest';
import { AdminApi } from '../infrastructure/admin-api';
import { InMemoryPublicConfigurationProvider } from '../infrastructure/public-configuration';
import { browserTransport, type Transport, type TransportRequest } from '../infrastructure/transport';

test('gets the stored setting and sends an explicit false on PATCH', async (): Promise<void> => {
  const requests: TransportRequest<unknown>[] = [];
  const transport: Transport = {
    async request<T>(request: TransportRequest<T>): Promise<T> {
      requests.push(request);
      if (!request.outputSchema) throw new Error('Missing response schema');
      if (request.requestBody?.kind !== 'json') return request.outputSchema.parse({ enabled: true });
      return request.outputSchema.parse(request.requestBody.schema.parse(request.requestBody.value));
    }
  };
  const route = new AdminApi(transport).portableConnectorSettings;
  const { signal } = new AbortController();
  await expect(route.get(signal)).resolves.toEqual({ enabled: true });
  await expect(route.update({ enabled: false }, signal)).resolves.toEqual({ enabled: false });
  expect(requests.map(({ method, path, signal, requestBody }) => [method, path, signal, requestBody?.kind === 'json' ? requestBody.value : undefined])).toEqual([
    ['GET', '/admin/system-settings/portable-connectors', signal, undefined],
    ['PATCH', '/admin/system-settings/portable-connectors', signal, { enabled: false }]
  ]);
});

test('rejects a non-boolean flag in the response', async (): Promise<void> => {
  const fetch = vi.fn<typeof globalThis.fetch>().mockResolvedValue(Response.json({ enabled: 'false' }));
  const configuration = new InMemoryPublicConfigurationProvider({ apiBaseUrl: '/api', mcpBaseUrl: '/mcp' });
  const route = new AdminApi(browserTransport({ fetch, configuration })).portableConnectorSettings;
  await expect(route.get(new AbortController().signal)).rejects.toMatchObject({ direction: 'inbound' });
});
