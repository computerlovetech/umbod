import { expect, it, vi } from 'vitest';
import { browserTransport, type Transport, type TransportRequest } from '#lib/admin/infrastructure/transport.js';
import { InMemoryPublicConfigurationProvider } from '#lib/admin/infrastructure/public-configuration.js';
import { telemetryInstallClaimRequestSchema, telemetryInstallClaimSchema } from '../domain/schemas';
import { HttpTelemetrySetupApi } from './api';

it('issues only a harness-bound claim through the authenticated transport', async (): Promise<void> => {
  const calls: TransportRequest<unknown>[] = [];
  const response = { code: 'A'.repeat(43) };
  const transport: Transport = {
    async request<T>(options: TransportRequest<T>): Promise<T> {
      calls.push(options);
      if (!options.outputSchema) throw new Error('Missing response schema');
      return options.outputSchema.parse(response);
    }
  };
  const { signal } = new AbortController();
  const request = { harness: 'codex' } as const;
  await expect(new HttpTelemetrySetupApi(transport).installClaims.create(request, signal)).resolves.toEqual(response);
  expect(calls).toEqual([{
    method: 'POST',
    path: '/me/telemetry/install-claims',
    requestBody: { kind: 'json', value: request, schema: telemetryInstallClaimRequestSchema },
    outputSchema: telemetryInstallClaimSchema,
    redirect: 'error',
    signal
  }]);
});

it.each([
  { code: 'A'.repeat(42) },
  { code: `'${'A'.repeat(42)}` },
  { code: 'A'.repeat(43), token: 'unexpected' }
])('rejects malformed or extra claim data', async (payload): Promise<void> => {
  const request = vi.fn<typeof fetch>().mockResolvedValue(Response.json(payload));
  const api = new HttpTelemetrySetupApi(browserTransport({
    fetch: request,
    configuration: new InMemoryPublicConfigurationProvider({ apiBaseUrl: '/api', mcpBaseUrl: '/mcp' })
  }));
  const { signal } = new AbortController();
  await expect(api.installClaims.create({ harness: 'claude-code' }, signal)).rejects.toMatchObject({
    name: 'SchemaValidationError', direction: 'inbound'
  });
  expect(request).toHaveBeenCalledExactlyOnceWith('/api/me/telemetry/install-claims', expect.objectContaining({
    method: 'POST',
    credentials: 'same-origin',
    redirect: 'error',
    body: '{"harness":"claude-code"}',
    signal
  }));
});
