import { describe, expect, test } from 'vitest';
import { z } from 'zod';
import type { Transport, TransportRequest } from '$lib/admin/infrastructure/transport';
import type { CataloguePort } from '../api';
import { catalogue } from '../test-fixtures';
import { CatalogueRoute } from './catalogue-route';
import { InMemoryDashboardApi } from './in-memory-api';

describe('user catalogue port', () => {
  test('in-memory adapter returns validated independent payloads', async (): Promise<void> => {
    const api = new InMemoryDashboardApi(catalogue);
    const port: CataloguePort = api.catalogue;
    const first = await port.list();
    first.connectors.length = 0;
    expect((await port.list()).connectors).toHaveLength(2);
  });

  test('HTTP adapter uses the user boundary and validates response through the transport', async (): Promise<void> => {
    const requests: TransportRequest<unknown>[] = [];
    const transport: Transport = {
      request: async <T>(request: TransportRequest<T>): Promise<T> => {
        requests.push(request);
        return request.outputSchema!.parse(catalogue);
      }
    };
    const port: CataloguePort = new CatalogueRoute(transport);
    const abort = new AbortController();
    expect(await port.list(abort.signal)).toEqual(catalogue);
    expect(requests[0].method).toBe('GET');
    expect(requests[0].path).toBe('/me/catalogue');
    expect(requests[0].signal).toBe(abort.signal);
    expect(() => requests[0].outputSchema!.parse({ ...catalogue, credentials: 'secret' })).toThrow(z.ZodError);
  });
});
