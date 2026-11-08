import { describe, expect, it } from 'vitest';
import { AnalyticsState } from './analytics-state.svelte';
import { InMemoryLogCounts } from './in-memory.test-support';
import { AuthenticationRequiredError, HttpError } from '../infrastructure/transport';
import type { LogCountResponse } from './domain/schemas';

const now = (): Date => new Date('2026-10-31T12:00:00Z');
const response: LogCountResponse = { has_more: false, rows: [
  { groups: [{ dimension: 'severity', value: { kind: 'missing' } }], count: 0, bucket: { kind: 'none' } },
  { groups: [{ dimension: 'severity', value: { kind: 'present', value: '' } }], count: 3, bucket: { kind: 'none' } }
] };

function setup(): { source: InMemoryLogCounts; state: AnalyticsState } {
  const source = new InMemoryLogCounts();
  source.response = response;
  const state = new AnalyticsState(source, now);
  state.setReport('custom');
  return { source, state };
}

describe('log-count query state', () => {
  it('pages submitted snapshots, retries failed pages and resets only on a new run', async (): Promise<void> => {
    const { source, state } = setup();
    source.response = { ...response, has_more: true };
    await state.run();
    const submitted = source.queries[0];
    state.draft.setPreset('custom');
    state.draft.selectFilter('source', 'draft');
    source.failure = new Error('offline');
    await state.next();
    expect(source.queries[1]).toEqual({ ...submitted, pagination: { limit: 100, offset: 100 } });
    expect(state.page).toBe(1);
    expect(state.result?.response.rows).toEqual(response.rows);
    expect(state.changed).toBe(true);
    source.failure = undefined;
    source.response = { rows: [], has_more: false };
    await state.retry();
    expect(source.queries[2]).toEqual(source.queries[1]);
    expect(state.page).toBe(2);
    expect(state.canGoNext).toBe(false);
    expect(state.canGoPrevious).toBe(true);
    expect(state.changed).toBe(true);
    await state.next();
    expect(source.queries).toHaveLength(3);
    await state.previous();
    expect(state.page).toBe(1);
    await state.previous();
    expect(source.queries).toHaveLength(4);
    state.draft.setPreset('day');
    await state.run();
    expect(source.queries[4].pagination).toEqual({ limit: 100, offset: 0 });
    expect(source.queries[4].filters).toEqual([{ dimension: 'source', values: ['draft'] }]);
    expect(state.changed).toBe(false);
  });

  it('disables navigation while pending and fences a late page after a new run', async (): Promise<void> => {
    const { source, state } = setup();
    source.response = { ...response, has_more: true };
    await state.run();
    let complete!: (value: LogCountResponse) => void;
    source.handler = () => new Promise((resolve) => { complete = resolve; });
    const page = state.next();
    expect(state.pending).toBe(true);
    expect(state.canGoPrevious).toBe(false);
    expect(state.canGoNext).toBe(false);
    await state.next();
    await state.previous();
    expect(source.queries).toHaveLength(2);
    source.handler = undefined;
    state.draft.setPreset('day');
    await state.run();
    expect(source.signals[1]?.aborted).toBe(true);
    complete({ rows: [], has_more: false });
    await page;
    expect(state.page).toBe(1);
    expect(state.result?.response.rows).toEqual(response.rows);
    expect(state.result?.query.time_range.start).toBe('2026-10-30T12:00:00.000Z');
  });

  it('snapshots ranges and filters, keeps drafts, and distinguishes zero, blank and missing groups', async (): Promise<void> => {
    const { source, state } = setup();
    state.draft.selectFilter('source', '');
    state.draft.selectFilter('source', ' exact ');
    await state.run();
    expect(source.queries[0]).toMatchObject({ time_range: { start: '2026-10-31T11:00:00.000Z', end: '2026-10-31T12:00:00.000Z' }, filters: [{ dimension: 'source', values: ['', ' exact '] }] });
    expect(state.total).toBe(3);
    expect(state.groupCount).toBe(2);
    expect(state.result?.response).toEqual(response);
    state.draft.toggleGroup('source');
    expect(state.draft.groupBy).toEqual(['severity', 'source']);
    expect(state.changed).toBe(true);
    expect(state.result?.query.group_by).toEqual(['severity']);
    expect(state.draft.filters.source).toEqual(['', ' exact ']);
  });

  it('shows zero observed groups for an empty ungrouped total', async (): Promise<void> => {
    const { source, state } = setup();
    state.draft.toggleGroup('severity');
    source.response = { has_more: false, rows: [{ groups: [], count: 0, bucket: { kind: 'none' } }] };
    await state.run();
    expect(state.total).toBe(0);
    expect(state.groupCount).toBe(0);
    expect(state.tableRows[0].count).toBe(0);
  });

  it('counts distinct groups across observed buckets without zero-filling', async (): Promise<void> => {
    const { source, state } = setup();
    state.draft.setPreset('week');
    state.draft.setBucket('day');
    source.response = { has_more: false, rows: [
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

  it('rejects reversed ranges, invalid offsets and invalid dates', async (): Promise<void> => {
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
    completions[1]({ has_more: false, rows: [] });
    await second;
    state.draft.setBucket('hour');
    completions[0](response);
    await first;
    expect(state.result?.response.rows).toEqual([]);
    expect(state.draft.bucket).toBe('hour');
    expect(state.result?.query.pagination).toEqual({ limit: 100, offset: 0 });
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
