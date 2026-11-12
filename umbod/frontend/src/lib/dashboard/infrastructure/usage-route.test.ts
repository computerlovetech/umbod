import { describe, expect, test } from 'vitest';
import type { Transport, TransportRequest } from '$lib/admin/infrastructure/transport';
import type { UsagePort } from '../api';
import { usageSnapshot } from '../usage-fixtures.test-support';
import { HttpDashboardApi } from './dashboard-api';

describe('personal usage route', () => {
  test.each([7, 30] as const)('requests only the %s day authenticated boundary with cancellation and validation', async (days): Promise<void> => {
    const requests: TransportRequest<unknown>[] = [];
    const transport: Transport = {
      request: async <T>(request: TransportRequest<T>): Promise<T> => {
        requests.push(request);
        return request.outputSchema!.parse(usageSnapshot(days));
      }
    };
    const port: UsagePort = new HttpDashboardApi(transport).usage;
    const abort = new AbortController();
    expect(await port.get(days, abort.signal)).toEqual(usageSnapshot(days));
    expect(requests[0].method).toBe('GET');
    expect(requests[0].path).toBe(`/me/usage?days=${days}`);
    expect(requests[0].signal).toBe(abort.signal);
    expect(requests[0].body).toBeUndefined();
    expect(requests[0].outputSchema!.safeParse({ ...usageSnapshot(days), identity_key: null }).success).toBe(false);
  });
});
