import { describe, expect, it, vi } from 'vitest';
import { browserTransport, type Transport, type TransportRequest } from '$lib/admin/infrastructure/transport';
import { InMemoryPublicConfigurationProvider } from '$lib/admin/infrastructure/public-configuration';
import { telemetrySetupSchema } from '../domain/schemas';
import { HttpTelemetrySetupApi } from './api';

describe('telemetry setup route', (): void => {
  it('declares the authenticated setup GET through the transport port', async (): Promise<void> => {
    const calls: TransportRequest<unknown>[] = [];
    const response = { status: 'available', logs_endpoint: 'https://custom.example/prefix/v1/logs' };
    const transport: Transport = {
      async request<T>(options: TransportRequest<T>): Promise<T> {
        calls.push(options);
        if (!options.outputSchema) throw new Error('Missing response schema');
        return options.outputSchema.parse(response);
      }
    };
    await expect(new HttpTelemetrySetupApi(transport).setup.get()).resolves.toEqual(response);
    expect(calls).toEqual([{ method: 'GET', path: '/me/telemetry/setup', outputSchema: telemetrySetupSchema }]);
  });

  it('uses the browser API base and validates malformed responses', async (): Promise<void> => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(Response.json({ status: 'available' }));
    const api = new HttpTelemetrySetupApi(browserTransport({
      fetch: request,
      configuration: new InMemoryPublicConfigurationProvider({ apiBaseUrl: '/api', mcpBaseUrl: '/mcp' })
    }));
    await expect(api.setup.get()).rejects.toMatchObject({ name: 'SchemaValidationError', direction: 'inbound' });
    expect(request).toHaveBeenCalledExactlyOnceWith('/api/me/telemetry/setup', expect.objectContaining({ method: 'GET', credentials: 'same-origin' }));
  });
});
