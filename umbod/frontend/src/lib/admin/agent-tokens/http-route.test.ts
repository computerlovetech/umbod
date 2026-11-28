import { describe, expect, it, vi } from 'vitest';
import { AdminApi } from '../infrastructure/admin-api';
import { InMemoryPublicConfigurationProvider } from '../infrastructure/public-configuration';
import { AuthenticationRequiredError, browserTransport, HttpError, SchemaValidationError, type Transport, type TransportRequest } from '../infrastructure/transport';
import type { AgentTokenMetadata, CreateAgentTokenInput, IssuedAgentToken, RotateAgentTokenInput } from './domain/schemas';
import type { AgentTokens } from './port';

const path = '/admin/tokens/agents';
const input: CreateAgentTokenInput = { display_name: 'Build agent', group_id: ' Release Team ', expires_at: '2099-01-01T00:00:00Z' };
const rotation: RotateAgentTokenInput = { expires_at: '2099-02-01T00:00:00+01:00' };
const metadata: AgentTokenMetadata = { ...input, agent_id: 'a'.repeat(32), credential_id: 'b'.repeat(32), status: 'active' };
const issued: IssuedAgentToken = { metadata, token: 'test-issued-token' };
const rotated: IssuedAgentToken = {
  metadata: { ...metadata, expires_at: '2099-01-31T23:00:00Z', credential_id: 'c'.repeat(32) },
  token: 'test-rotated-token'
};

class RecordingTransport implements Transport {
  readonly requests: TransportRequest<unknown>[] = [];

  constructor(private readonly responses: readonly unknown[]) {}

  async request<T>(request: TransportRequest<T>): Promise<T> {
    const response = this.responses[this.requests.length];
    this.requests.push(request);
    if (request.requestBody?.kind === 'json') request.requestBody.schema.parse(request.requestBody.value);
    return request.outputSchema ? request.outputSchema.parse(response) : undefined as T;
  }
}

function browserClient(response: Response): { api: AgentTokens; fetch: ReturnType<typeof vi.fn<typeof globalThis.fetch>> } {
  const fetch = vi.fn<typeof globalThis.fetch>().mockResolvedValue(response);
  const configuration = new InMemoryPublicConfigurationProvider({ apiBaseUrl: '/api', mcpBaseUrl: '/mcp' });
  return { api: new AdminApi(browserTransport({ fetch, configuration })).agentTokens, fetch };
}

describe('agent token HTTP adapter', (): void => {
  it('lists metadata and sends lifecycle commands through the admin transport', async (): Promise<void> => {
    const rows: AgentTokenMetadata[] = [
      { ...metadata, agent_id: 'd'.repeat(32), credential_id: 'e'.repeat(32), status: 'expired' },
      { ...metadata, status: 'revoked' }
    ];
    const transport = new RecordingTransport([rows, issued, rotated, undefined]);
    const api: AgentTokens = new AdminApi(transport).agentTokens;

    await expect(api.list()).resolves.toEqual(rows);
    await expect(api.create(input)).resolves.toEqual(issued);
    await expect(api.rotate(metadata.agent_id, rotation)).resolves.toEqual(rotated);
    await expect(api.revoke(metadata.agent_id)).resolves.toBeUndefined();
    expect(transport.requests.map(({ method, path, requestBody }) => [
      method, path, requestBody?.kind === 'json' ? requestBody.schema.parse(requestBody.value) : undefined
    ])).toEqual([
      ['GET', path, undefined],
      ['POST', path, input],
      ['POST', `${path}/${metadata.agent_id}/rotate`, rotation],
      ['DELETE', `${path}/${metadata.agent_id}`, undefined]
    ]);
  });

  it('sends and reads an explicit null expiration', async (): Promise<void> => {
    const nonExpiring = { ...issued, metadata: { ...metadata, expires_at: null } };
    const transport = new RecordingTransport([nonExpiring, nonExpiring, [nonExpiring.metadata]]);
    const api = new AdminApi(transport).agentTokens;

    await expect(api.create({ ...input, expires_at: null })).resolves.toEqual(nonExpiring);
    await expect(api.rotate(metadata.agent_id, { expires_at: null })).resolves.toEqual(nonExpiring);
    await expect(api.list()).resolves.toEqual([nonExpiring.metadata]);
    expect(transport.requests[0]?.requestBody).toMatchObject({ value: { expires_at: null } });
    expect(transport.requests[1]?.requestBody).toMatchObject({ value: { expires_at: null } });
  });

  it('accepts a raw empty array and adds the API base only once', async (): Promise<void> => {
    const { api, fetch } = browserClient(Response.json([]));
    await expect(api.list()).resolves.toEqual([]);
    expect(fetch).toHaveBeenCalledExactlyOnceWith(`/api${path}`, expect.objectContaining({ method: 'GET' }));
  });

  it('revokes without a request body and accepts an empty 204', async (): Promise<void> => {
    const { api, fetch } = browserClient(new Response(null, { status: 204 }));
    await expect(api.revoke(metadata.agent_id)).resolves.toBeUndefined();
    expect(fetch).toHaveBeenCalledExactlyOnceWith(`/api${path}/${metadata.agent_id}`, expect.objectContaining({
      method: 'DELETE', headers: { 'X-Umbod-Web-Request': '1' }, credentials: 'same-origin'
    }));
    expect(fetch.mock.calls[0]?.[1]?.body).toBeUndefined();
  });

  it.each([
    { ...input, display_name: ' \t' },
    { ...input, group_id: '' },
    { ...input, expires_at: '2099-01-01T00:00:00' },
    { ...input, status: 'active' }
  ])('rejects invalid creation bodies before fetch', async (body: CreateAgentTokenInput): Promise<void> => {
    const { api, fetch } = browserClient(Response.json(issued));
    await expect(api.create(body)).rejects.toMatchObject({ direction: 'outbound' });
    expect(fetch).not.toHaveBeenCalled();
  });

  it('rejects an invalid rotation expiry before fetch', async (): Promise<void> => {
    const { api, fetch } = browserClient(Response.json(rotated));
    await expect(api.rotate(metadata.agent_id, { expires_at: '2099-01-01' })).rejects.toMatchObject({ direction: 'outbound' });
    expect(fetch).not.toHaveBeenCalled();
  });

  it('rejects invalid agent IDs before fetch', async (): Promise<void> => {
    const { api, fetch } = browserClient(Response.json(rotated));
    await expect(api.rotate('../rotate', rotation)).rejects.toMatchObject({ direction: 'outbound' });
    await expect(api.revoke(metadata.agent_id.toUpperCase())).rejects.toMatchObject({ direction: 'outbound' });
    expect(fetch).not.toHaveBeenCalled();
  });

  it.each([
    { case: 'wrapped response', payload: { agents: [metadata] } },
    { case: 'unknown status', payload: [{ ...metadata, status: 'unknown' }] },
    { case: 'credential in metadata', payload: [{ ...metadata, token: issued.token }] }
  ])('rejects an invalid list: $case', async ({ payload }: { payload: unknown }): Promise<void> => {
    const { api } = browserClient(Response.json(payload));
    await expect(api.list()).rejects.toMatchObject({ direction: 'inbound' });
  });

  it.each(['create', 'rotate'] as const)('rejects a missing or empty issued credential from %s', async (operation: 'create' | 'rotate'): Promise<void> => {
    const missing = browserClient(Response.json({ metadata }));
    const empty = browserClient(Response.json({ metadata, token: '' }));
    for (const { api } of [missing, empty]) {
      const result = operation === 'create' ? api.create(input) : api.rotate(metadata.agent_id, rotation);
      await expect(result).rejects.toBeInstanceOf(SchemaValidationError);
    }
  });

  it('preserves the existing authentication and HTTP error mapping', async (): Promise<void> => {
    const unauthorized = browserClient(new Response(null, { status: 401 }));
    await expect(unauthorized.api.list()).rejects.toBeInstanceOf(AuthenticationRequiredError);
    const forbidden = browserClient(Response.json({ detail: 'Forbidden' }, { status: 403 }));
    const result = forbidden.api.list();
    await expect(result).rejects.toBeInstanceOf(HttpError);
    await expect(result).rejects.toMatchObject({ status: 403, body: { detail: 'Forbidden' } });
  });
});
