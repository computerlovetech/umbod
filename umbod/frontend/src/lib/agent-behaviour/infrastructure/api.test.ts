import { expect, test, vi } from 'vitest';
import { browserTransport, SchemaValidationError } from '#lib/admin/infrastructure/transport.js';
import { AgentBehaviourApi, ConfigurationRoute } from './api';
import { PersonalAgentBehaviourApi } from './personal-api';
import { storedReport } from '../in-memory.test-support';
import type { Transport, TransportRequest } from '#lib/admin/infrastructure/transport.js';
import { configurationSchema } from '../domain/schemas';

function fixture(): { api: AgentBehaviourApi; request: ReturnType<typeof vi.fn<typeof fetch>> } {
  const request = vi.fn<typeof fetch>();
  const api = new AgentBehaviourApi(browserTransport({ fetch: request, configuration: { get: async () => ({ apiBaseUrl: '/api', mcpBaseUrl: '/mcp', filesystemPreviewMaxBytes: 257 }) } }));
  return { api, request };
}

test('publishes a validated atomic revision command and parses response', async (): Promise<void> => {
  const { api, request } = fixture(); request.mockResolvedValue(new Response(JSON.stringify({ revision: 2, patterns: [], playbooks: [] })));
  const command = { expected_revision: 1, patterns: [], playbooks: [] }; expect(await api.configuration.publish(command)).toEqual({ revision: 2, patterns: [], playbooks: [] });
  expect(request).toHaveBeenCalledWith('/api/admin/agent-behaviour/configuration', expect.objectContaining({ method: 'PUT', body: JSON.stringify(command) }));
});

test('rejects invalid publication before network and malformed responses at boundary', async (): Promise<void> => {
  const { api, request } = fixture(); await expect(api.configuration.publish({ expected_revision: -1, patterns: [], playbooks: [] })).rejects.toBeInstanceOf(SchemaValidationError); expect(request).not.toHaveBeenCalled();
  request.mockResolvedValue(new Response(JSON.stringify({ revision: 'bad', patterns: [], playbooks: [] }))); await expect(api.configuration.get()).rejects.toBeInstanceOf(SchemaValidationError);
});

test('encodes all report filters and handles empty deletion responses', async (): Promise<void> => {
  const { api, request } = fixture(); request.mockResolvedValueOnce(new Response(JSON.stringify({ items: [], total: 0 }))).mockResolvedValueOnce(new Response(null, { status: 204 }));
  await api.reports.list({ limit: 25, offset: 50, playbook_id: 'review', pattern_id: 'fallback', status: 'not_assessed' }); expect(request).toHaveBeenNthCalledWith(1, '/api/admin/agent-behaviour/reports?limit=25&offset=50&playbook_id=review&pattern_id=fallback&status=not_assessed', expect.objectContaining({ method: 'GET' }));
  await expect(api.reports.remove('id')).resolves.toBeUndefined();
});

test('reads and validates personal list and detail using only the owner-scoped paths', async (): Promise<void> => {
  const request = vi.fn<typeof fetch>();
  const api = new PersonalAgentBehaviourApi(browserTransport({ fetch: request, configuration: { get: async () => ({ apiBaseUrl: '/api/', mcpBaseUrl: '/mcp', filesystemPreviewMaxBytes: 257 }) } }));
  const signal = new AbortController().signal;
  const report = storedReport();
  request
    .mockResolvedValueOnce(Response.json({ items: [], total: 0 }))
    .mockResolvedValueOnce(Response.json(report))
    .mockResolvedValueOnce(Response.json({ items: [], total: -1 }))
    .mockResolvedValueOnce(Response.json({ report_id: report.report_id }));

  await expect(api.reports.list({ limit: 10, offset: 20, playbook_id: 'review', pattern_id: 'fallback', status: 'observed' }, signal)).resolves.toEqual({ items: [], total: 0 });
  await expect(api.reports.get(report.report_id, signal)).resolves.toEqual(report);
  await expect(api.reports.list({ limit: 10, offset: 0 })).rejects.toBeInstanceOf(SchemaValidationError);
  await expect(api.reports.get(report.report_id)).rejects.toBeInstanceOf(SchemaValidationError);
  expect(request).toHaveBeenNthCalledWith(1, '/api/me/agent-behaviour/reports?limit=10&offset=20&playbook_id=review&pattern_id=fallback&status=observed', expect.objectContaining({ method: 'GET', signal }));
  expect(request).toHaveBeenNthCalledWith(2, `/api/me/agent-behaviour/reports/${report.report_id}`, expect.objectContaining({ method: 'GET', signal }));
  expect(request.mock.calls.every(([path, init]): boolean => typeof path === 'string' && path.startsWith('/api/me/agent-behaviour/reports') && init?.method === 'GET')).toBe(true);
});

test('loads backend-owned defaults through the validated configuration route', async (): Promise<void> => {
  const signal = new AbortController().signal;
  const captured: TransportRequest<unknown>[] = [];
  const transport: Transport = {
    request: async <T>(options: TransportRequest<T>): Promise<T> => {
      captured.push(options);
      if (!options.outputSchema) throw new Error('Response schema required');
      return options.outputSchema.parse({ revision: 1, patterns: [], playbooks: [] });
    }
  };
  expect(await new ConfigurationRoute(transport).defaults(signal)).toEqual({ revision: 1, patterns: [], playbooks: [] });
  expect(captured).toEqual([{ method: 'GET', path: '/admin/agent-behaviour/defaults', outputSchema: configurationSchema, signal }]);
});

test('rejects malformed defaults at the HTTP boundary', async (): Promise<void> => {
  const { api, request } = fixture();
  request.mockResolvedValue(new Response(JSON.stringify({ revision: 1, patterns: [{ id: 'invalid' }], playbooks: [] })));
  await expect(api.configuration.defaults()).rejects.toBeInstanceOf(SchemaValidationError);
});
