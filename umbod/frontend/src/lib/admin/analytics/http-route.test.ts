import { describe, expect, it, vi } from 'vitest';
import { AdminApi } from '../infrastructure/admin-api';
import { browserTransport, HttpError, SchemaValidationError } from '../infrastructure/transport';
import { InMemoryPublicConfigurationProvider } from '../infrastructure/public-configuration';
import { logCountQuerySchema, logCountResponseSchema, type LogCountQuery } from './domain/schemas';

const query: LogCountQuery = {
  time_range: { start: '2026-10-31T09:00:00Z', end: '2026-10-31T10:00:00Z' },
  filters: [{ dimension: 'source', values: ['', 'api'] }], group_by: ['source', 'severity'],
  bucketing: { kind: 'fixed', width: 'minute' }, max_groups: 100
};

function client(payload: unknown, status = 200): { api: AdminApi; request: ReturnType<typeof vi.fn<typeof fetch>> } {
  const request = vi.fn<typeof fetch>().mockResolvedValue(new Response(JSON.stringify(payload), { status, headers: { 'content-type': 'application/json' } }));
  const api = new AdminApi(browserTransport({ fetch: request, configuration: new InMemoryPublicConfigurationProvider({ apiBaseUrl: '/api', mcpBaseUrl: '/mcp' }) }));
  return { api, request };
}

describe('analytics route and wire contract', () => {
  it('posts the validated body through the composite client to the administrator endpoint', async (): Promise<void> => {
    const { api, request } = client({ rows: [] });
    expect(await api.analytics.query(query)).toEqual({ rows: [] });
    expect(request).toHaveBeenCalledWith('/api/admin/telemetry/log-counts', expect.objectContaining({ method: 'POST', body: JSON.stringify(query), credentials: 'same-origin' }));
  });

  it('rejects malformed outbound requests before network access', async (): Promise<void> => {
    const { api, request } = client({ rows: [] });
    await expect(api.analytics.query({ ...query, max_groups: 1001 })).rejects.toBeInstanceOf(SchemaValidationError);
    expect(request).not.toHaveBeenCalled();
  });

  it.each([
    { rows: [{ groups: [], count: -1, bucket: { kind: 'none' } }] },
    { rows: [{ groups: [{ dimension: 'unknown', value: { kind: 'missing' } }], count: 2, bucket: { kind: 'none' } }] },
    { rows: [{ groups: [], count: 2, bucket: { kind: 'bucket', start: 'not a timestamp' } }] },
    { rows: [{ groups: [], count: 2.5, bucket: { kind: 'none' } }] },
    { rows: null }
  ])('rejects malformed responses at the transport boundary', async (payload: unknown): Promise<void> => {
    const { api } = client(payload);
    await expect(api.analytics.query(query)).rejects.toBeInstanceOf(SchemaValidationError);
  });

  it('accepts complete aggregate rows and preserves missing versus empty values', async (): Promise<void> => {
    const payload = { rows: [{
      groups: [{ dimension: 'source', value: { kind: 'present', value: '' } }, { dimension: 'severity', value: { kind: 'missing' } }],
      count: 2, bucket: { kind: 'bucket', start: '2026-10-31T09:00:00Z' }
    }] };
    const { api } = client(payload);
    expect(await api.analytics.query(query)).toEqual(payload);
  });

  it.each([
    { rows: [{ groups: [], count: 2, bucket: { kind: 'bucket', start: '2026-10-31T09:00:00Z' } }] },
    { rows: [{ groups: [{ dimension: 'source', value: { kind: 'missing' } }, { dimension: 'severity', value: { kind: 'missing' } }], count: 2, bucket: { kind: 'none' } }] }
  ])('rejects rows that do not match submitted grouping or bucketing', async (payload: unknown): Promise<void> => {
    const { api } = client(payload);
    await expect(api.analytics.query(query)).rejects.toBeInstanceOf(SchemaValidationError);
  });

  it('retains actionable server errors', async (): Promise<void> => {
    const { api } = client({ detail: 'Narrow your filters' }, 422);
    await expect(api.analytics.query(query)).rejects.toMatchObject({ status: 422, body: { detail: 'Narrow your filters' } } satisfies Partial<HttpError>);
  });

  it('enforces unique dimensions, aware ranges and instance-owned scope', (): void => {
    expect(logCountQuerySchema.safeParse({ ...query, group_by: ['source', 'source'] }).success).toBe(false);
    expect(logCountQuerySchema.safeParse({ ...query, filters: [query.filters[0], query.filters[0]] }).success).toBe(false);
    expect(logCountQuerySchema.safeParse({ ...query, scope: 'instance' }).success).toBe(false);
    expect(logCountQuerySchema.safeParse({ ...query, time_range: { start: '2026-10-31T09:00:00', end: query.time_range.end } }).success).toBe(false);
    expect(logCountQuerySchema.safeParse({ ...query, filters: [{ dimension: 'source', values: [] }] }).success).toBe(false);
    expect(logCountQuerySchema.safeParse({ ...query, filters: [{ dimension: 'source', values: ['codex', 'codex'] }] }).success).toBe(false);
    expect(logCountResponseSchema.parse({ rows: [{ groups: [{ dimension: 'source', value: { kind: 'present', value: '' } }], count: 0, bucket: { kind: 'none' } }] }).rows[0].count).toBe(0);
  });
});
