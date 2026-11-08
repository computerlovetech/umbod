import { describe, expect, it, vi } from 'vitest';
import { AuthenticationRequiredError, browserTransport, HttpError, SchemaValidationError, type Transport, type TransportRequest } from '$lib/admin/infrastructure/transport';
import { PersonalAccessTokensApi } from './api';
import { createdTokenSchema, createTokenSchema } from '../domain/schemas';
import { InMemoryPersonalAccessTokens } from '../in-memory-api.test-support';

class MemoryTransport implements Transport {
  requests: TransportRequest<unknown>[] = [];
  response: unknown = undefined;
  async request<T>(request: TransportRequest<T>): Promise<T> {
    this.requests.push(request);
    request.inputSchema?.parse(request.body);
    return request.outputSchema ? request.outputSchema.parse(this.response) : undefined as T;
  }
}

const input = { name: 'Agent', expires_at: '2099-01-01T00:00:00Z', permissions: { telemetry: 'write' as const } };

describe('personal access token routes', (): void => {
  it('validates list, creation and revocation over the transport port', async (): Promise<void> => {
    const memory = new InMemoryPersonalAccessTokens();
    const issued = await memory.create(input);
    const transport = new MemoryTransport();
    const api = new PersonalAccessTokensApi(transport);
    transport.response = [issued.metadata];
    expect(await api.tokens.list()).toEqual([issued.metadata]);
    transport.response = issued;
    expect(await api.tokens.create(input)).toEqual(issued);
    await api.tokens.revoke(issued.metadata.token_id);
    expect(transport.requests.map((request: TransportRequest<unknown>): string => request.method + ' ' + request.path)).toEqual([
      'GET /me/personal-access-tokens', 'POST /me/personal-access-tokens', 'DELETE /me/personal-access-tokens/' + issued.metadata.token_id
    ]);
    expect(transport.requests[1].inputSchema).toBe(createTokenSchema);
    expect(transport.requests[1].outputSchema).toBe(createdTokenSchema);
    expect(() => api.tokens.revoke('../bad')).toThrow();
  });
  it('blocks invalid outbound payloads and rejects malformed responses', async (): Promise<void> => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(new Response('{}'));
    const api = new PersonalAccessTokensApi(browserTransport({ fetch: request, configuration: { get: async () => ({ apiBaseUrl: '/api', mcpBaseUrl: '/mcp' }) } }));
    await expect(api.tokens.create({ ...input, name: '' })).rejects.toBeInstanceOf(SchemaValidationError);
    expect(request).not.toHaveBeenCalled();
    await expect(api.tokens.create(input)).rejects.toBeInstanceOf(SchemaValidationError);
  });
  it.each([401, 403])('maps HTTP %s without navigation', async (status: number): Promise<void> => {
    const api = new PersonalAccessTokensApi(browserTransport({ fetch: async (): Promise<Response> => new Response(null, { status }), configuration: { get: async () => ({ apiBaseUrl: '/api', mcpBaseUrl: '/mcp' }) } }));
    await expect(api.tokens.list()).rejects.toBeInstanceOf(status === 401 ? AuthenticationRequiredError : HttpError);
  });
  it('uses web request protection and accepts empty revocation responses', async (): Promise<void> => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(new Response(null, { status: 204 }));
    const api = new PersonalAccessTokensApi(browserTransport({ fetch: request, configuration: { get: async () => ({ apiBaseUrl: '/api', mcpBaseUrl: '/mcp' }) } }));
    await api.tokens.revoke('a'.repeat(32));
    expect(request).toHaveBeenCalledWith('/api/me/personal-access-tokens/' + 'a'.repeat(32), expect.objectContaining({ method: 'DELETE', headers: expect.objectContaining({ 'X-Umbod-Web-Request': '1' }) }));
  });
});
