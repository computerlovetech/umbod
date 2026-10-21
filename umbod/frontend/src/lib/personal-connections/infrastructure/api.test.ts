import { describe, expect, test, vi } from 'vitest';
import { AuthenticationRequiredError, browserTransport, HttpError, type Transport, type TransportRequest } from '$lib/admin/infrastructure/transport';
import { InMemoryPublicConfigurationProvider } from '$lib/admin/infrastructure/public-configuration';
import { authorizationHealthSchema, emptyRequestSchema, renewalResultSchema, type AuthorizationHealth } from '../domain/schemas';
import type { PersonalConnectionsApi } from '../api';
import { InMemoryPersonalConnectionsApi } from './in-memory-api';
import { HttpPersonalConnectionsApi } from './personal-connections-api';
import { authorizationHealth, selection, pendingAttempt, completedAttempt } from '../test-fixtures';

describe('personal connections API port', () => {
  test('reads are passive and returned projections are isolated', async () => {
    const api: PersonalConnectionsApi = new InMemoryPersonalConnectionsApi([selection], { calendar: authorizationHealth });
    const first = await api.connections.get(selection.connector_id);
    first.enabled = false;
    expect(await api.connections.list()).toEqual({ connectors: [selection] });
  });
  test('replacement cancellation preserves saved authorization; disconnect disables and removes it', async () => {
    const api: PersonalConnectionsApi = new InMemoryPersonalConnectionsApi([selection], { calendar: authorizationHealth });
    const attempt = await api.authorization.start(selection.connector_id, {});
    await expect(api.authorization.start(selection.connector_id, {})).rejects.toThrow();
    expect((await api.connections.get(selection.connector_id)).has_authorization).toBe(true);
    expect((await api.authorization.cancel(selection.connector_id, attempt.attempt_id)).status).toBe('cancelled');
    expect((await api.connections.get(selection.connector_id)).has_authorization).toBe(true);
    await api.connections.disconnect(selection.connector_id);
    expect(await api.connections.get(selection.connector_id)).toMatchObject({ enabled: false, has_authorization: false });
  });
  test('disable invalidates attempts without deleting authorization or automatically reenabling', async () => {
    const api: PersonalConnectionsApi = new InMemoryPersonalConnectionsApi([selection], { calendar: authorizationHealth });
    const attempt = await api.authorization.start(selection.connector_id, {});
    expect(await api.connections.setEnablement(selection.connector_id, { enabled: false })).toMatchObject({ enabled: false, has_authorization: true });
    expect((await api.authorization.get(selection.connector_id, attempt.attempt_id)).status).toBe('cancelled');
    await expect(api.authorization.start(selection.connector_id, {})).rejects.toThrow();
    await expect(api.connections.discover(selection.connector_id, {})).rejects.toThrow();
  });
});

class RecordingTransport implements Transport {
  readonly requests: TransportRequest<unknown>[] = [];
  constructor(private readonly responses: unknown[]) {}
  request = async <T>(request: TransportRequest<T>): Promise<T> => {
    this.requests.push(request);
    if (request.body !== undefined) request.inputSchema?.parse(request.body);
    const payload = this.responses.shift();
    if (payload instanceof Error) throw payload;
    return request.outputSchema ? request.outputSchema.parse(payload) : undefined as T;
  };
}

describe('HTTP route adapter contracts through Transport', () => {
  test('encodes identifiers, uses validated exact bodies and omits output schemas for 204', async () => {
    const transport = new RecordingTransport([{ connectors: [selection] }, selection, selection, undefined, pendingAttempt, completedAttempt, completedAttempt, undefined]);
    const api: PersonalConnectionsApi = new HttpPersonalConnectionsApi(transport);
    const id = 'id/with ?#';
    const aid = 'attempt/?#';
    await api.connections.list();
    await api.connections.get(id);
    await api.connections.setEnablement(id, { enabled: false });
    await api.connections.disconnect(id);
    await api.authorization.start(id, {});
    await api.authorization.get(id, aid);
    await api.authorization.cancel(id, aid);
    await api.connections.discover(id, {});
    const base = '/me/connectors/mcp/id%2Fwith%20%3F%23';
    expect(transport.requests.map(({ method, path }) => [method, path])).toEqual([
      ['GET', '/me/connectors/mcp'], ['GET', base], ['PUT', base + '/enablement'],
      ['DELETE', base + '/authorization'], ['POST', base + '/oauth/attempts'],
      ['GET', base + '/oauth/attempts/attempt%2F%3F%23'], ['DELETE', base + '/oauth/attempts/attempt%2F%3F%23'],
      ['POST', base + '/tools/discovery']
    ]);
    expect(transport.requests[2].body).toEqual({ enabled: false });
    for (const index of [4, 7]) {
      expect(transport.requests[index].body).toEqual({});
      expect(transport.requests[index].inputSchema?.safeParse({ owner: 'forbidden' }).success).toBe(false);
    }
    for (const index of [3, 7]) expect(transport.requests[index].outputSchema).toBeUndefined();
  });
  test.each([new AuthenticationRequiredError(), new HttpError(403, 'Forbidden', { detail: 'private' })])('preserves authentication errors without retry', async (error) => {
    const transport = new RecordingTransport([error]);
    const api: PersonalConnectionsApi = new HttpPersonalConnectionsApi(transport);
    await expect(api.connections.list()).rejects.toBe(error);
    expect(transport.requests).toHaveLength(1);
  });
  test('health and renewal have distinct encoded routes, strict empty input and literal validated output', async (): Promise<void> => {
    const transport = new RecordingTransport([authorizationHealth, { status: 'refreshed', discovery_required: true }]);
    const api: PersonalConnectionsApi = new HttpPersonalConnectionsApi(transport);
    expect(await api.authorization.getHealth('a/b')).toEqual(authorizationHealth);
    expect(await api.authorization.renew('a/b', {})).toEqual({ status: 'refreshed', discovery_required: true });
    expect(transport.requests.map(({ method, path, body }) => ({ method, path, body }))).toEqual([
      { method: 'GET', path: '/me/connectors/mcp/a%2Fb/authorization', body: undefined },
      { method: 'POST', path: '/me/connectors/mcp/a%2Fb/authorization/refresh', body: {} }
    ]);
    expect(transport.requests[1].inputSchema?.safeParse({ owner: 'forbidden' }).success).toBe(false);
  });
  test.each([
    { state: 'not_authorized' }, authorizationHealth,
    { state: 'expired', expires_at: '2030-01-01T00:00:00+01:00', refresh_supported: true },
    { state: 'unsupported' },
    { state: 'reconnect_required', reason: 'provider_rejected' },
    { state: 'reconnect_required', reason: 'refresh_uncertain' },
    { state: 'reconnect_required', reason: 'refresh_denied' },
    { state: 'refreshing', deadline: '2030-01-01T00:00:00Z' }
  ])('validates health $state through both public adapters', async (payload): Promise<void> => {
    const health: AuthorizationHealth = authorizationHealthSchema.parse(payload);
    const adapters: PersonalConnectionsApi[] = [
      new InMemoryPersonalConnectionsApi([selection], { calendar: health }),
      new HttpPersonalConnectionsApi(new RecordingTransport([payload]))
    ];
    for (const api of adapters) expect(await api.authorization.getHealth('calendar')).toEqual(health);
  });
  test.each([
    { state: 'authorized' },
    { state: 'authorized', expires_at: '2030-01-01T00:00:00', refresh_supported: true },
    { state: 'expired', expires_at: 'bad', refresh_supported: true },
    { state: 'reconnect_required', reason: 'unknown' },
    { state: 'refreshing', deadline: 'bad' },
    { state: 'unknown' },
    { state: 'unsupported', token: 'private' }
  ])('rejects malformed health without fallback: %j', async (payload): Promise<void> => {
    const api: PersonalConnectionsApi = new HttpPersonalConnectionsApi(new RecordingTransport([payload]));
    await expect(api.authorization.getHealth('calendar')).rejects.toThrow();
  });
  test.each([
    { status: 'refreshed', discovery_required: false },
    { status: 'refreshed' },
    { status: 'unknown', discovery_required: true }
  ])('rejects malformed renewal output: %j', async (payload): Promise<void> => {
    const api: PersonalConnectionsApi = new HttpPersonalConnectionsApi(new RecordingTransport([payload]));
    await expect(api.authorization.renew('calendar', {})).rejects.toThrow();
  });
  test.each([new AuthenticationRequiredError(), new HttpError(403, 'Forbidden', {}), new HttpError(404, 'Not found', {})])('preserves health and renewal auth errors without retries', async (error): Promise<void> => {
    const transport = new RecordingTransport([error, error]);
    const api: PersonalConnectionsApi = new HttpPersonalConnectionsApi(transport);
    await expect(api.authorization.getHealth('calendar')).rejects.toBe(error);
    await expect(api.authorization.renew('calendar', {})).rejects.toBe(error);
    expect(transport.requests).toHaveLength(2);
  });
  test('memory requires explicit health, never inferring it from saved authorization', async (): Promise<void> => {
    const api: PersonalConnectionsApi = new InMemoryPersonalConnectionsApi([selection]);
    await expect(api.authorization.getHealth('calendar')).rejects.toThrow();
  });
  test('browser transport validates strict renewal input before network and rejects invalid output', async (): Promise<void> => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(Response.json({ status: 'refreshed', discovery_required: false }));
    const configuration = new InMemoryPublicConfigurationProvider({ apiBaseUrl: '/api', mcpBaseUrl: 'https://mcp.example' });
    const transport: Transport = browserTransport({ fetch: request, configuration });
    const api: PersonalConnectionsApi = new HttpPersonalConnectionsApi(transport);
    await expect(transport.request({
      method: 'POST', path: '/me/connectors/mcp/calendar/authorization/refresh',
      body: { owner: 'forbidden' }, inputSchema: emptyRequestSchema, outputSchema: renewalResultSchema
    })).rejects.toMatchObject({ direction: 'outbound' });
    expect(request).not.toHaveBeenCalled();
    await expect(api.authorization.renew('calendar', {})).rejects.toMatchObject({ direction: 'inbound' });
    expect(request).toHaveBeenCalledOnce();
  });
  test('browser adapter accepts real empty 204 and validates start URL without navigation', async () => {
    const request = vi.fn<typeof fetch>().mockResolvedValueOnce(new Response(null, { status: 204 })).mockResolvedValueOnce(Response.json({ ...pendingAttempt, authorization_url: 'http://unsafe.example' }, { status: 201 }));
    const configuration = new InMemoryPublicConfigurationProvider({ apiBaseUrl: '/api', mcpBaseUrl: 'https://mcp.example' });
    const api: PersonalConnectionsApi = new HttpPersonalConnectionsApi(browserTransport({ fetch: request, configuration }));
    await expect(api.connections.discover('calendar', {})).resolves.toBeUndefined();
    await expect(api.authorization.start('calendar', {})).rejects.toMatchObject({ direction: 'inbound' });
    expect(request).toHaveBeenCalledTimes(2);
    expect(request).toHaveBeenNthCalledWith(1, '/api/me/connectors/mcp/calendar/tools/discovery', expect.objectContaining({
      credentials: 'same-origin', body: '{}', headers: { 'X-Umbod-Web-Request': '1', 'content-type': 'application/json' }
    }));
  });
});
