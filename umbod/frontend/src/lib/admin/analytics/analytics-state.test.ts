import { describe, expect, it } from 'vitest';
import { AnalyticsState } from './analytics-state.svelte';
import { InMemoryLogCounts } from './in-memory.test-support';
import { AuthenticationRequiredError, HttpError } from '../infrastructure/transport';
import type { LogCountResponse } from './domain/schemas';

const now = (): Date => new Date('2026-10-31T12:00:00Z');
const response: LogCountResponse = { rows: [
  { groups: [{ dimension: 'severity', value: { kind: 'missing' } }], count: 0, bucket: { kind: 'none' } },
  { groups: [{ dimension: 'severity', value: { kind: 'present', value: '' } }], count: 3, bucket: { kind: 'none' } }
] };

function setup(): { source: InMemoryLogCounts; state: AnalyticsState } {
  const source = new InMemoryLogCounts();
  source.response = response;
  return { source, state: new AnalyticsState(source, now) };
}

describe('log-count query state', () => {
  it('snapshots ranges and filters, keeps drafts, and distinguishes zero, blank and missing groups', async (): Promise<void> => {
    const { source, state } = setup();
    state.draft.addFilter('source');
    state.draft.setInput('source', ' exact ');
    state.draft.addFilter('source');
    await state.run();
    expect(source.queries[0]).toMatchObject({ time_range: { start: '2026-10-31T11:00:00.000Z', end: '2026-10-31T12:00:00.000Z' }, filters: [{ dimension: 'source', values: ['', ' exact '] }] });
    expect(state.total).toBe(3);
    expect(state.groupCount).toBe(2);
    expect(state.result?.response).toEqual(response);
    state.draft.toggleGroup('source');
    state.draft.moveGroup('source', -1);
    expect(state.draft.groupBy).toEqual(['source', 'severity']);
    expect(state.changed).toBe(true);
    expect(state.result?.query.group_by).toEqual(['severity']);
    expect(state.draft.filters.source).toEqual(['', ' exact ']);
  });

  it('shows zero observed groups for an empty ungrouped total', async (): Promise<void> => {
    const { source, state } = setup();
    state.draft.toggleGroup('severity');
    source.response = { rows: [{ groups: [], count: 0, bucket: { kind: 'none' } }] };
    await state.run();
    expect(state.total).toBe(0);
    expect(state.groupCount).toBe(0);
    expect(state.tableRows[0].count).toBe(0);
  });

  it('counts distinct groups across observed buckets without zero-filling', async (): Promise<void> => {
    const { source, state } = setup();
    state.draft.setPreset('week');
    state.draft.setBucket('day');
    source.response = { rows: [
      { groups: [{ dimension: 'severity', value: { kind: 'present', value: 'INFO' } }], count: 2, bucket: { kind: 'bucket', start: '2026-10-25T00:00:00Z' } },
      { groups: [{ dimension: 'severity', value: { kind: 'present', value: 'INFO' } }], count: 4, bucket: { kind: 'bucket', start: '2026-10-30T00:00:00Z' } }
    ] };
    await state.run();
    expect(source.queries[0].time_range.start).toBe('2026-10-24T12:00:00.000Z');
    expect(state.total).toBe(6);
    expect(state.groupCount).toBe(1);
    expect(state.tableRows).toHaveLength(2);
  });

  it('converts explicit offsets to UTC, independently of browser timezone', async (): Promise<void> => {
    const { source, state } = setup();
    state.draft.setPreset('custom');
    state.draft.setStart('2026-10-31T09:00');
    state.draft.setEnd('2026-10-31T10:00');
    state.draft.setOffset('+05:30');
    state.draft.setBucket('hour');
    await state.run();
    expect(source.queries[0].time_range).toEqual({ start: '2026-10-31T03:30:00.000Z', end: '2026-10-31T04:30:00.000Z' });
    expect(source.queries[0].bucketing).toEqual({ kind: 'fixed', width: 'hour' });
  });

  it.each(['0', '1001', '1.5', 'NaN', ''])('rejects invalid limits %s without a request', async (limit: string): Promise<void> => {
    const { source, state } = setup();
    state.draft.setLimit(limit);
    await state.run();
    expect(source.queries).toHaveLength(0);
    expect(state.validation).not.toBe('');
  });

  it('rejects reversed ranges, invalid offsets, invalid dates and unadded values', async (): Promise<void> => {
    const { source, state } = setup();
    state.draft.setPreset('custom');
    state.draft.setStart('2026-10-31T10:00');
    state.draft.setEnd('2026-10-31T09:00');
    await state.run();
    expect(state.validation).toContain('start before end');
    state.draft.setOffset('+14:30');
    await state.run();
    expect(state.validation).toContain('UTC offset');
    state.draft.setOffset('+00:00');
    state.draft.setStart('2026-02-30T01:00');
    await state.run();
    expect(state.validation).toContain('valid custom dates');
    state.draft.setInput('source', 'unadded');
    await state.run();
    expect(state.validation).toContain('Add or clear');
    expect(source.queries).toHaveLength(0);
  });

  it('ignores obsolete responses and preserves edits made during a pending request', async (): Promise<void> => {
    const { source, state } = setup();
    const completions: Array<(value: LogCountResponse) => void> = [];
    source.handler = () => new Promise((resolve) => completions.push(resolve));
    const first = state.run();
    expect(state.pending).toBe(true);
    state.draft.setPreset('day');
    const second = state.run();
    completions[1]({ rows: [] });
    await second;
    state.draft.setLimit('50');
    completions[0](response);
    await first;
    expect(state.result?.response.rows).toEqual([]);
    expect(state.draft.limit).toBe('50');
    expect(state.result?.query.max_groups).toBe(100);
    expect(state.changed).toBe(true);
    expect(state.pending).toBe(false);
  });

  it('fences disposed requests and clears privileged data', async (): Promise<void> => {
    const { source, state } = setup();
    await state.run();
    let complete: (value: LogCountResponse) => void = () => {};
    source.handler = () => new Promise((resolve) => { complete = resolve; });
    const pending = state.run();
    state.dispose();
    complete(response);
    await pending;
    expect(state.result).toBeUndefined();
    expect(state.pending).toBe(false);
    await state.run();
    expect(source.queries).toHaveLength(2);
  });

  it.each([new AuthenticationRequiredError(), new HttpError(401, 'Unauthorized', {}), new HttpError(403, 'Forbidden', {})])('clears results on access loss', async (failure: Error): Promise<void> => {
    const { source, state } = setup();
    await state.run();
    source.failure = failure;
    await state.run();
    expect(state.accessLost).toBe(true);
    expect(state.result).toBeUndefined();
    expect(state.error).toContain('Administration access');
  });

  it.each([
    [new HttpError(503, 'Unavailable', {}), 'disabled'],
    [new HttpError(422, 'Unprocessable', { detail: 'Narrow grouping to stay within the limit' }), 'Narrow grouping'],
    [new Error('offline'), 'try again']
  ])('shows recoverable failures and supports retry', async (failure: Error, message: string): Promise<void> => {
    const { source, state } = setup();
    source.failure = failure;
    await state.run();
    expect(state.error).toContain(message);
    expect(state.pending).toBe(false);
    source.failure = undefined;
    await state.run();
    expect(state.error).toBe('');
    expect(state.total).toBe(3);
  });
});
