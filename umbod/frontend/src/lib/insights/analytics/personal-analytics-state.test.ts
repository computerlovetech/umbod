import { describe, expect, it, vi } from 'vitest';
import { logCountQuerySchema, type LogCountQuery, type LogCountResponse } from '#lib/admin/analytics/domain/schemas.js';
import { InMemoryPublicConfigurationProvider } from '#lib/admin/infrastructure/public-configuration.js';
import { browserTransport } from '#lib/admin/infrastructure/transport.js';
import { createPersonalAnalyticsState } from './personal-analytics-state';
import { PersonalLogCountRoute } from './personal-log-count-route';

const personalPath = '/api/me/telemetry/log-counts';
const emptyPage: LogCountResponse = { rows: [], has_more: false };
const now = (): Date => new Date('2026-10-31T12:00:00Z');

function createTransport(fetch: typeof globalThis.fetch): ReturnType<typeof browserTransport> {
  return browserTransport({
    fetch,
    configuration: new InMemoryPublicConfigurationProvider({ apiBaseUrl: '/api', mcpBaseUrl: '/mcp' })
  });
}

describe('personal log analytics', (): void => {
  it('uses only the owner endpoint for stored logs, session drill-down and filter choices', async (): Promise<void> => {
    const calls: Array<{ url: string; query: LogCountQuery }> = [];
    const request = vi.fn<typeof fetch>(async (input, init): Promise<Response> => {
      expect(init).toMatchObject({
        method: 'POST', credentials: 'same-origin', redirect: 'error',
        headers: { 'X-Umbod-Web-Request': '1', 'content-type': 'application/json' }
      });
      const query = logCountQuerySchema.parse(JSON.parse(String(init?.body)));
      calls.push({ url: String(input), query });
      return Response.json({
        rows: [{
          bucket: { kind: 'none' },
          groups: query.group_by.map((dimension) => ({ dimension, value: { kind: 'present', value: dimension === 'session_id' ? 'session-1' : 'codex' } })),
          count: 2
        }],
        has_more: false
      });
    });
    const state = createPersonalAnalyticsState(createTransport(request), now);

    expect(await state.start()).toBe(true);
    expect(state.result?.report).toBe('logs');
    const session = state.tableRows[0].groups.find((group) => group.dimension === 'session_id');
    if (!session) throw new Error('Expected a session group');
    expect(state.isSessionGroup(session)).toBe(true);
    await state.narrowToSession('session-1');
    expect(state.narrowedSession).toBe('session-1');
    await state.allSessions();
    expect(state.narrowedSession).toBeUndefined();

    state.setReport('tools');
    expect(await state.run()).toBe(true);
    expect(state.result?.report).toBe('tools');

    state.setReport('custom');
    await state.choices.show();
    expect(state.choices.options).toEqual([{ value: '"codex"', label: 'codex (2)' }]);
    state.choices.choose('"codex"');
    expect(await state.run()).toBe(true);
    expect(calls.map(({ url }) => url)).toEqual(Array(6).fill(personalPath));
    expect(calls.map(({ query }) => query.filters)).toEqual([
      [], [{ dimension: 'session_id', values: ['session-1'] }], [],
      [{ dimension: 'activity_kind', values: ['tool_call', 'file_read', 'file_edit'] }],
      [], [{ dimension: 'source', values: ['codex'] }]
    ]);
  });

  it('clears results and does not fall back when access is denied during a filter lookup', async (): Promise<void> => {
    const request = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(Response.json(emptyPage))
      .mockResolvedValueOnce(Response.json({}, { status: 403 }));
    const state = createPersonalAnalyticsState(createTransport(request), now);

    expect(await state.start()).toBe(true);
    state.setReport('custom');
    await state.choices.show();
    await state.retry();

    expect(state.accessLost).toBe(true);
    expect(state.result).toBeUndefined();
    expect(state.choices.open).toBe(false);
    expect(state.error).toBe('Access to your logs is no longer available. Sign in again to continue.');
    expect(request.mock.calls.map(([url]) => url)).toEqual([personalPath, personalPath]);
  });

  it('retries temporary unavailability on the owner endpoint', async (): Promise<void> => {
    const request = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(Response.json({}, { status: 503 }))
      .mockResolvedValueOnce(Response.json(emptyPage));
    const state = createPersonalAnalyticsState(createTransport(request), now);

    expect(await state.start()).toBe(false);
    expect(state.error).toBe('Personal log analytics is currently unavailable. Try again later.');
    expect(state.accessLost).toBe(false);
    await state.retry();
    expect(state.error).toBe('');
    expect(state.result?.response).toEqual(emptyPage);
    expect(request.mock.calls.map(([url]) => url)).toEqual([personalPath, personalPath]);
  });

  it('refuses owner overrides and results that do not match the requested grouping', async (): Promise<void> => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(Response.json({
      rows: [{ groups: [], count: 1, bucket: { kind: 'none' } }], has_more: false
    }));
    const route = new PersonalLogCountRoute(createTransport(request));
    const query: LogCountQuery = {
      time_range: { start: '2026-10-31T11:00:00Z', end: now().toISOString() },
      filters: [], group_by: ['source'], bucketing: { kind: 'none' }, pagination: { offset: 0, limit: 100 }
    };
    const otherOwnerQuery = { ...query, scope: 'instance' };
    await expect(route.query(otherOwnerQuery)).rejects.toMatchObject({ direction: 'outbound' });
    expect(request).not.toHaveBeenCalled();
    await expect(route.query(query)).rejects.toMatchObject({ direction: 'inbound' });
    expect(request.mock.calls.map(([url]) => url)).toEqual([personalPath]);
  });
});
