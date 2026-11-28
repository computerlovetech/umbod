import { expect, test } from 'vitest';
import type { Transport, TransportRequest } from '../infrastructure/transport.js';
import { submittedConnector, unconfiguredConnector } from './fixtures.test-support.js';
import { PortableConnectorsRoute } from './http-route.js';

test('uses only the portable catalog and configuration operations with validated wire bodies', async (): Promise<void> => {
  const requests: TransportRequest<unknown>[] = [];
  const configuration = { workspace: 'Team', mode: 'preview' };
  const saved = { ...unconfiguredConnector, connector: { ...submittedConnector, configured: true }, configuration };
  const transport: Transport = {
    request: async <T>(request: TransportRequest<T>): Promise<T> => {
      requests.push(request);
      if (!request.outputSchema) throw new Error('A response schema is required.');
      if (request.path.endsWith('/configuration')) {
        if (request.method === 'GET') return request.outputSchema.parse(unconfiguredConnector);
        if (request.requestBody?.kind !== 'json') throw new Error('A validated JSON body is required.');
        const { schema, value } = request.requestBody;
        expect(schema.parse(value)).toEqual({ configuration });
        expect(schema.safeParse({ configuration, status: 'active' }).success).toBe(false);
        expect(schema.safeParse({ configuration: { workspace: 42 } }).success).toBe(false);
        return request.outputSchema.parse(saved);
      }
      expect(request.outputSchema.safeParse({ connectors: [{ ...submittedConnector, status: 'active' }] }).success).toBe(false);
      expect(request.outputSchema.safeParse({ connectors: [{ ...submittedConnector, connector_id: 'wrong' }] }).success).toBe(false);
      return request.outputSchema.parse({ connectors: [submittedConnector] });
    }
  };
  const api = new PortableConnectorsRoute(transport);
  const { signal } = new AbortController();
  const path = `/admin/portable-connectors/${submittedConnector.connector_id}/configuration`;
  await expect(api.list()).resolves.toEqual({ connectors: [submittedConnector] });
  await expect(api.getConfiguration(submittedConnector.connector_id, signal)).resolves.toEqual(unconfiguredConnector);
  await expect(api.replaceConfiguration(submittedConnector.connector_id, { configuration }, signal)).resolves.toEqual(saved);
  expect(requests.map(({ method, path, signal }) => ({ method, path, signal }))).toEqual([
    { method: 'GET', path: '/admin/portable-connectors', signal: undefined },
    { method: 'GET', path, signal },
    { method: 'PUT', path, signal }
  ]);
});
