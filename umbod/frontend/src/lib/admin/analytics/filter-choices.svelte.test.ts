import { describe, expect, it, vi } from 'vitest';
import { AnalyticsState } from './analytics-state.svelte';
import { AuthenticationRequiredError, HttpError } from '../infrastructure/transport';
import type { Dimension, LogCountQuery, LogCountResponse } from './domain/schemas';
import type { LogCountSource } from './port';

function values(dimension: Dimension = 'source'): LogCountResponse {
  return { has_more: false, rows: [
    { groups: [{ dimension, value: { kind: 'missing' } }], count: 8, bucket: { kind: 'none' } },
    ...['', ' Alpha ', 'alpha', 'Beta'].map((value, index) => ({ groups: [{ dimension, value: { kind: 'present' as const, value } }], count: index + 1, bucket: { kind: 'none' as const } }))
  ] };
}

class Source implements LogCountSource {
  readonly queries: LogCountQuery[] = [];
  readonly signals: Array<AbortSignal | undefined> = [];
  response = values();
  failure: Error | undefined;
  handler: (() => Promise<LogCountResponse>) | undefined;

  async query(query: LogCountQuery, signal?: AbortSignal): Promise<LogCountResponse> {
    this.queries.push(query);
    this.signals.push(signal);
    if (this.failure) throw this.failure;
    return this.handler ? this.handler() : this.response;
  }
}

function setup(): { source: Source; state: AnalyticsState } {
  const source = new Source();
  return { source, state: new AnalyticsState(source, () => new Date('2026-10-31T12:00:00Z')) };
}

function deferred(): { promise: Promise<LogCountResponse>; resolve: (response: LogCountResponse) => void; reject: (error: Error) => void } {
  let resolve!: (response: LogCountResponse) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<LogCountResponse>((complete, fail) => { resolve = complete; reject = fail; });
  return { promise, resolve, reject };
}

describe('existing filter choices', () => {
  it('collects every server page before exposing choices within a fixed resolved range', async (): Promise<void> => {
    const { source, state } = setup();
    const final = deferred();
    source.response = { ...values(), has_more: true };
    source.handler = async (): Promise<LogCountResponse> => {
      if (source.queries.length === 1) return source.response;
      return final.promise;
    };
    const loading = state.choices.show();
    await vi.waitFor(() => expect(source.queries).toHaveLength(2));
    expect(source.queries.map((query) => query.pagination)).toEqual([{ limit: 1000, offset: 0 }, { limit: 1000, offset: 1000 }]);
    expect(source.queries[1].time_range).toEqual(source.queries[0].time_range);
    expect(state.choices.options).toEqual([]);
    expect(state.choices.pending).not.toBe('');
    final.resolve({ has_more: false, rows: [{ groups: [{ dimension: 'source', value: { kind: 'present', value: 'last' } }], count: 1, bucket: { kind: 'none' } }] });
    await loading;
    expect(state.choices.options).toHaveLength(5);
    expect(state.choices.options.at(-1)?.label).toBe('last (1)');
  });

  it('keeps repeated live-page values unique with the latest observed count', async (): Promise<void> => {
    const { source, state } = setup();
    source.handler = async (): Promise<LogCountResponse> => source.queries.length === 1
      ? { ...values(), has_more: true }
      : { has_more: false, rows: [{ groups: [{ dimension: 'source', value: { kind: 'present', value: 'Beta' } }], count: 5, bucket: { kind: 'none' } }] };
    await state.choices.show();
    expect(source.queries).toHaveLength(2);
    expect(state.choices.options).toHaveLength(4);
    expect(state.choices.options.filter((entry) => entry.value === '"Beta"')).toEqual([{ value: '"Beta"', label: 'Beta (5)' }]);
    state.choices.choose('"Beta"');
    expect(state.draft.filters.source).toEqual(['Beta']);
    expect(state.choices.options).toHaveLength(3);
  });

  it('aborts discovery between pages without displaying partial choices', async (): Promise<void> => {
    const { source, state } = setup();
    const final = deferred();
    source.handler = async (): Promise<LogCountResponse> => source.queries.length === 1
      ? { ...values(), has_more: true } : final.promise;
    const loading = state.choices.show();
    await vi.waitFor(() => expect(source.queries).toHaveLength(2));
    state.choices.close();
    expect(source.signals[1]?.aborted).toBe(true);
    final.resolve({ ...values(), has_more: true });
    await loading;
    expect(source.queries).toHaveLength(2);
    expect(state.choices.options).toEqual([]);
  });

  it('discovers unfiltered values for one dimension and preserves exact blank, whitespace and case', async (): Promise<void> => {
    const { source, state } = setup();
    state.draft.selectFilter('severity', 'INFO');
    state.draft.setBucket('hour');
    await state.choices.show();
    expect(state.choices.dimension).toBe('source');
    expect(source.queries[0]).toEqual({ time_range: { start: '2026-10-31T11:00:00.000Z', end: '2026-10-31T12:00:00.000Z' }, filters: [], group_by: ['source'], bucketing: { kind: 'none' }, pagination: { limit: 1000, offset: 0 } });
    expect(state.choices.options).toEqual([
      { value: '""', label: 'Empty value (1)' }, { value: '" Alpha "', label: ' Alpha  (2)' },
      { value: '"alpha"', label: 'alpha (3)' }, { value: '"Beta"', label: 'Beta (4)' }
    ]);
    state.choices.setSearch('EMPTY');
    expect(state.choices.options).toEqual([{ value: '""', label: 'Empty value (1)' }]);
    const choose = state.choices.choose;
    choose('""');
    choose('" Alpha "');
    choose('"alpha"');
    choose('"alpha"');
    choose('not json');
    expect(state.draft.filters.source).toEqual(['', ' Alpha ', 'alpha']);
    expect(state.choices.options).toEqual([{ value: '"Beta"', label: 'Beta (4)' }]);
  });

  it('adds an exact manual session independently of discovery without duplicates or extra requests', async (): Promise<void> => {
    const { source, state } = setup();
    state.setReport('custom');
    state.draft.selectFilter('source', 'client');
    await state.choices.show();
    source.failure = new Error('offline');
    await state.choices.setDimension('session_id');
    expect(state.choices.error).not.toBe('');
    expect(state.choices.canAddSession).toBe(false);
    state.choices.setManualSession(' exact session ');
    expect(state.choices.canAddSession).toBe(true);
    state.choices.addSession();
    expect(state.draft.filters.session_id).toEqual([' exact session ']);
    expect(state.draft.filters.source).toEqual(['client']);
    expect(state.choices.manualSession).toBe('');
    expect(source.queries).toHaveLength(2);
    state.choices.setManualSession(' exact session ');
    expect(state.choices.canAddSession).toBe(false);
    state.choices.addSession();
    expect(state.draft.filters.session_id).toEqual([' exact session ']);
    source.failure = undefined;
    await state.run();
    expect(source.queries[2].filters).toEqual([{ dimension: 'source', values: ['client'] }, { dimension: 'session_id', values: [' exact session '] }]);
    state.dispose();
  });

  it('guards manual session entry after closure, dimension changes and disposal', async (): Promise<void> => {
    const { state } = setup();
    state.setReport('custom');
    await state.choices.show();
    await state.choices.setDimension('session_id');
    state.choices.setManualSession('discarded');
    state.choices.close();
    expect(state.choices.manualSession).toBe('');
    state.choices.setManualSession('closed');
    state.choices.addSession();
    expect(state.draft.filters.session_id).toEqual([]);
    await state.choices.show();
    await state.choices.setDimension('source');
    expect(state.choices.manualSession).toBe('');
    state.choices.setManualSession('wrong dimension');
    state.choices.addSession();
    expect(state.draft.filters.session_id).toEqual([]);
    await state.choices.setDimension('session_id');
    state.dispose();
    state.choices.setManualSession('disposed');
    state.choices.addSession();
    expect(state.draft.filters.session_id).toEqual([]);
  });

  it('requires a valid time range before making a discovery request', async (): Promise<void> => {
    const { source, state } = setup();
    state.draft.setPreset('custom');
    await state.choices.show();
    expect(state.choices.error).toContain('valid time range');
    expect(state.choices.pending).toBe('');
    expect(source.queries).toHaveLength(0);
    state.draft.setStart('2026-10-31T10:00');
    state.draft.setEnd('2026-10-31T11:00');
    await state.choices.refresh();
    expect(state.choices.options).toHaveLength(4);
  });

  it('searches locally without case folding selected values and resets search on choice and dimension change', async (): Promise<void> => {
    const { source, state } = setup();
    await state.choices.show();
    const search = state.choices.setSearch;
    search('ALP');
    expect(state.choices.options).toHaveLength(2);
    state.choices.choose('"alpha"');
    expect(state.choices.search).toBe('');
    search('unknown');
    expect(state.choices.emptyMessage).toContain('No matching');
    expect(source.queries).toHaveLength(1);
    await state.choices.setDimension('invalid');
    expect(state.choices.dimension).toBe('source');
    source.response = values('tool_name');
    await state.choices.setDimension('tool_name');
    expect(state.choices.search).toBe('');
    expect(source.queries[1].group_by).toEqual(['tool_name']);
    expect(state.choices.options).toHaveLength(4);
  });

  it('distinguishes no present attributes from an empty value', async (): Promise<void> => {
    const { source, state } = setup();
    source.response = { has_more: false, rows: [values().rows[0], { groups: [], count: 4, bucket: { kind: 'none' } }] };
    await state.choices.show();
    expect(state.choices.options).toEqual([]);
    expect(state.choices.emptyMessage).toContain('No unselected');
  });

  it.each([
    [new HttpError(422, 'Invalid query', {}), 'query settings'],
    [new Error('offline'), 'try again'],
    [new HttpError(503, 'Unavailable', {}), 'try again']
  ])('clears old options on failure and supports refresh', async (failure: Error, message: string): Promise<void> => {
    const { source, state } = setup();
    await state.choices.show();
    source.failure = failure;
    await state.choices.refresh();
    expect(state.choices.options).toEqual([]);
    expect(state.choices.error).toContain(message);
    expect(state.choices.pending).toBe('');
    source.failure = undefined;
    await state.choices.refresh();
    expect(state.choices.error).toBe('');
    expect(state.choices.options).toHaveLength(4);
  });

  it('uses time configuration rather than the clock, buckets, groups or filters for freshness', async (): Promise<void> => {
    const source = new Source();
    let clock = new Date('2026-10-31T12:00:00Z');
    const state = new AnalyticsState(source, () => clock);
    await state.choices.show();
    clock = new Date('2026-11-01T12:00:00Z');
    state.draft.setBucket('day');
    state.draft.toggleGroup('source');
    state.draft.selectFilter('severity', 'INFO');
    expect(state.choices.stale).toBe(false);
    for (const update of [() => state.draft.setPreset('day'), () => state.draft.setStart('2026-10-30T00:00'), () => state.draft.setEnd('2026-10-31T00:00'), () => state.draft.setOffset('+01:00')]) {
      update();
      expect(state.choices.stale).toBe(true);
      expect(state.choices.options).toEqual([]);
      expect(state.choices.emptyMessage).toContain('Refresh');
      state.choices.choose('"alpha"');
      expect(state.draft.filters.source).toEqual([]);
      await state.choices.refresh();
      expect(state.choices.stale).toBe(false);
    }
  });

  it.each(['close', 'dispose', 'dimension', 'refresh'] as const)('fences late responses after %s', async (action): Promise<void> => {
    const { source, state } = setup();
    const late = deferred();
    source.handler = () => late.promise;
    const loading = state.choices.show();
    expect(state.choices.pending).not.toBe('');
    source.handler = undefined;
    source.response = { has_more: false, rows: [] };
    if (action === 'close') state.choices.close();
    if (action === 'dispose') state.dispose();
    if (action === 'dimension') await state.choices.setDimension('severity');
    if (action === 'refresh') await state.choices.refresh();
    expect(source.signals[0]?.aborted).toBe(true);
    late.resolve(values());
    await loading;
    expect(state.choices.options).toEqual([]);
    expect(state.choices.pending).toBe('');
  });

  it('hides responses when time changes during discovery until explicitly refreshed', async (): Promise<void> => {
    const { source, state } = setup();
    const late = deferred();
    source.handler = () => late.promise;
    const loading = state.choices.show();
    state.draft.setPreset('week');
    late.resolve(values());
    await loading;
    expect(state.choices.stale).toBe(true);
    expect(state.choices.options).toEqual([]);
  });

  it.each([new AuthenticationRequiredError(), new HttpError(401, 'Unauthorized', {}), new HttpError(403, 'Forbidden', {})])('revokes analytics access and fences a concurrent result', async (failure: Error): Promise<void> => {
    const { source, state } = setup();
    await state.run();
    expect(state.result).toBeDefined();
    const late = deferred();
    source.handler = () => late.promise;
    const running = state.run();
    source.failure = failure;
    await state.choices.show();
    expect(state.accessLost).toBe(true);
    expect(state.result).toBeUndefined();
    expect(state.pending).toBe(false);
    expect(state.choices.pending).toBe('');
    expect(source.signals[1]?.aborted).toBe(true);
    late.resolve(values());
    await running;
    expect(state.result).toBeUndefined();
    expect(state.error).toContain('Administration access');
    await state.run();
    await state.choices.show();
    expect(source.queries).toHaveLength(3);
  });

  it('query access loss aborts discovery and ignores its late failure', async (): Promise<void> => {
    const { source, state } = setup();
    const late = deferred();
    source.handler = () => late.promise;
    const loading = state.choices.show();
    source.failure = new AuthenticationRequiredError();
    await state.run();
    late.reject(new Error('late'));
    await loading;
    expect(state.choices.error).toBe('');
    expect(state.choices.pending).toBe('');
    expect(state.choices.open).toBe(false);
    expect(source.signals[0]?.aborted).toBe(true);
  });
});
