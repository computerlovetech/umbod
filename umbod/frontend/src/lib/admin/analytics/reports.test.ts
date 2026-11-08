import { describe, expect, it, vi } from 'vitest';
import { AnalyticsState } from './analytics-state.svelte';
import { InMemoryLogCounts, isClassificationQuery } from './in-memory.test-support';
import { dimensions, logCountQuerySchema, logCountResponseSchema, type LogCountResponse } from './domain/schemas';
import { HttpError } from '../infrastructure/transport';

const now = (): Date => new Date('2026-10-31T12:00:00Z');

describe('session activity reports', () => {
  it.each([
    ['tools', ['tool_call', 'file_read', 'file_edit'], ['source', 'session_id', 'outcome'], 'Reported tool calls'],
    ['files', ['file_read', 'file_edit'], ['source', 'session_id', 'activity_kind'], 'Read/edit-tool calls'],
    ['skills', ['skill_activation'], ['source', 'session_id'], 'Skill activations']
  ])('submits the canonical %s contract for all sessions without custom settings', async (report, activities, groups, countLabel): Promise<void> => {
    const source = new InMemoryLogCounts();
    const state = new AnalyticsState(source, now);
    expect(state.report).toBe('tools');
    state.draft.selectFilter('tool_name', 'ignored');
    state.draft.setBucket('hour');
    state.setReport(report);
    state.reportRange.setPreset('day');
    expect(source.reportQueries).toHaveLength(0);
    await state.run();
    expect(source.reportQueries[0]).toEqual({
      time_range: { start: '2026-10-30T12:00:00.000Z', end: '2026-10-31T12:00:00.000Z' },
      filters: [{ dimension: 'activity_kind', values: activities }],
      group_by: groups,
      bucketing: { kind: 'none' },
      pagination: { limit: 100, offset: 0 }
    });
    expect(state.countLabel).toBe(countLabel);
    expect(state.changed).toBe(false);
    state.dispose();
  });

  it('omits the session filter for all sessions and keeps custom settings independent', async (): Promise<void> => {
    const source = new InMemoryLogCounts();
    const state = new AnalyticsState(source, now);
    await state.run();
    expect(source.reportQueries[0].filters).toEqual([{ dimension: 'activity_kind', values: ['tool_call', 'file_read', 'file_edit'] }]);
    state.setReport('custom');
    state.draft.setPreset('week');
    state.draft.setBucket('day');
    state.draft.selectFilter('outcome', 'unsupported');
    state.draft.toggleGroup('activity_kind');
    await state.run();
    const custom = source.reportQueries[1];
    state.setReport('files');
    state.reportRange.setPreset('day');
    await state.run();
    state.setReport('custom');
    await state.run();
    expect(source.reportQueries[3]).toEqual(custom);
    state.dispose();
  });

  it('freezes submitted report metadata, query and absolute range through navigation and retry', async (): Promise<void> => {
    const source = new InMemoryLogCounts();
    source.response = { rows: [], has_more: true };
    const state = new AnalyticsState(source, now);
    await state.run();
    const submitted = source.reportQueries[0];
    state.setReport('custom');
    state.draft.setPreset('week');
    source.failure = new Error('offline');
    await state.next();
    expect(state.resultLabel).toBe('Tool calls');
    expect(state.countLabel).toBe('Reported tool calls');
    source.failure = undefined;
    state.setReport('skills');
    await state.retry();
    expect(source.reportQueries[2]).toEqual({ ...submitted, pagination: { limit: 100, offset: 100 } });
    expect(state.result?.report).toBe('tools');
    expect(state.changed).toBe(true);
    expect(state.page).toBe(2);
    await state.previous();
    expect(source.reportQueries[3]).toEqual(submitted);
    state.dispose();
  });

  it.each(['tools', 'files', 'skills', 'logs'])('drills into %s results and returns to all sessions using the frozen submitted query', async (report): Promise<void> => {
    const source = new InMemoryLogCounts();
    source.response = { rows: [], has_more: true };
    const state = new AnalyticsState(source, now);
    state.setReport(report);
    await state.run();
    const submitted = source.reportQueries[0];
    await state.next();
    state.setReport('custom');
    state.draft.setPreset('week');
    state.draft.selectFilter('session_id', 'custom draft');
    state.reportRange.setPreset('custom');
    state.reportRange.setStart('invalid');
    await state.narrowToSession(' exact session ');
    const narrowed = { ...submitted, filters: [...submitted.filters, { dimension: 'session_id', values: [' exact session '] }], pagination: { limit: 100, offset: 0 } };
    expect(source.reportQueries[2]).toEqual(narrowed);
    expect(state.result?.report).toBe(report);
    expect(state.narrowedSession).toBe(' exact session ');
    expect(state.page).toBe(1);
    expect(state.changed).toBe(true);
    await state.next();
    expect(source.reportQueries[3]).toEqual({ ...narrowed, pagination: { limit: 100, offset: 100 } });
    await state.allSessions();
    expect(source.reportQueries[4]).toEqual(submitted);
    expect(state.narrowedSession).toBeUndefined();
    expect(state.page).toBe(1);
    expect(state.report).toBe('custom');
    expect(state.draft.filters.session_id).toEqual(['custom draft']);
    expect(state.changed).toBe(true);
    state.dispose();
  });

  it.each(['narrow', 'clear'])('retries a failed session %s without changing the previous successful scope', async (operation): Promise<void> => {
    const source = new InMemoryLogCounts();
    const state = new AnalyticsState(source, now);
    await state.run();
    if (operation === 'clear') await state.narrowToSession('selected');
    const previous = state.result;
    source.failure = new Error('offline');
    await (operation === 'clear' ? state.allSessions() : state.narrowToSession('selected'));
    const failedQuery = source.reportQueries[source.reportQueries.length - 1];
    expect(state.result).toBe(previous);
    expect(state.error).not.toBe('');
    state.setReport('skills');
    state.reportRange.setPreset('week');
    source.failure = undefined;
    await state.retry();
    expect(source.reportQueries[source.reportQueries.length - 1]).toEqual(failedQuery);
    expect(state.result?.report).toBe('tools');
    expect(state.narrowedSession).toBe(operation === 'clear' ? undefined : 'selected');
    expect(state.error).toBe('');
    state.dispose();
  });

  it('ignores duplicate session actions while pending and fences a superseded drill-down', async (): Promise<void> => {
    const source = new InMemoryLogCounts();
    source.response = { rows: [], has_more: true };
    const state = new AnalyticsState(source, now);
    await state.run();
    let complete!: (value: LogCountResponse) => void;
    source.handler = (query) => isClassificationQuery(query) ? Promise.resolve(source.classificationResponse) : new Promise((resolve) => { complete = resolve; });
    const pending = state.narrowToSession('selected');
    await state.narrowToSession('other');
    await state.allSessions();
    await state.next();
    expect(source.reportQueries).toHaveLength(2);
    expect(state.pending).toBe(true);
    source.handler = undefined;
    state.setReport('files');
    await state.run();
    expect(source.signals[2]?.aborted).toBe(true);
    complete({ rows: [], has_more: false });
    await pending;
    expect(state.result?.report).toBe('files');
    expect(state.narrowedSession).toBeUndefined();
    state.dispose();
    await state.narrowToSession('ignored');
    await state.allSessions();
    expect(source.reportQueries).toHaveLength(3);
  });

  it('keeps custom session filtering separate and starts fresh standard runs across all sessions', async (): Promise<void> => {
    const source = new InMemoryLogCounts();
    const state = new AnalyticsState(source, now);
    await state.narrowToSession('ignored');
    await state.allSessions();
    expect(source.reportQueries).toHaveLength(0);
    state.setReport('custom');
    state.draft.selectFilter('session_id', 'manual');
    await state.run();
    await state.narrowToSession('ignored');
    await state.allSessions();
    expect(source.reportQueries).toHaveLength(1);
    expect(state.narrowedSession).toBeUndefined();
    expect(source.reportQueries[0].filters).toEqual([{ dimension: 'session_id', values: ['manual'] }]);
    state.setReport('tools');
    await state.run();
    await state.narrowToSession('selected');
    await state.narrowToSession('');
    expect(state.narrowedSession).toBe('selected');
    await state.run();
    expect(state.narrowedSession).toBeUndefined();
    expect(source.reportQueries[3].filters).toEqual([{ dimension: 'activity_kind', values: ['tool_call', 'file_read', 'file_edit'] }]);
    expect(state.changed).toBe(false);
    state.dispose();
  });

  it('formats only canonical report values and leaves custom values untouched', async (): Promise<void> => {
    const source = new InMemoryLogCounts();
    const state = new AnalyticsState(source, now);
    await state.run();
    expect(state.formatValue('outcome', 'success')).toBe('Successful');
    expect(state.formatValue('outcome', 'failure')).toBe('Failed');
    expect(state.formatValue('outcome', 'unknown')).toBe('Unknown outcome');
    expect(state.formatValue('activity_kind', 'file_read')).toBe('Read-tool calls');
    expect(state.formatValue('activity_kind', 'file_edit')).toBe('Edit-tool calls');
    expect(state.formatValue('source', '')).toBe('Not reported');
    state.setReport('custom');
    await state.run();
    expect(state.formatValue('outcome', 'unknown')).toBe('unknown');
    expect(state.formatValue('outcome', 'unsupported')).toBe('unsupported');
    state.dispose();
  });

  it('fences late report completions after disposal and access loss', async (): Promise<void> => {
    const source = new InMemoryLogCounts();
    const state = new AnalyticsState(source, now);
    let complete!: (value: LogCountResponse) => void;
    source.handler = (query) => isClassificationQuery(query) ? Promise.resolve(source.classificationResponse) : new Promise((resolve) => { complete = resolve; });
    const pending = state.run();
    source.handler = undefined;
    source.failure = new HttpError(403, 'Forbidden', {});
    await state.run();
    expect(source.signals[0]?.aborted).toBe(true);
    complete({ rows: [], has_more: true });
    await pending;
    expect(state.accessLost).toBe(true);
    expect(state.result).toBeUndefined();
    state.dispose();
    await state.retry();
    expect(source.reportQueries).toHaveLength(2);
  });

  it('automatically counts successful standard scopes without blocking results, caches paging and preserves counts on primary failure', async (): Promise<void> => {
    const source = new InMemoryLogCounts();
    const state = new AnalyticsState(source, now);
    let complete!: (value: LogCountResponse) => void;
    source.handler = (query) => isClassificationQuery(query) ? new Promise((resolve) => { complete = resolve; }) : Promise.resolve({ rows: [], has_more: true });
    await state.run();
    expect(state.pending).toBe(false);
    expect(state.result).toBeDefined();
    expect(state.coverage.pending).toBe(true);
    expect(source.queries).toHaveLength(2);
    complete({ rows: [{ groups: [{ dimension: 'activity_kind', value: { kind: 'missing' } }], count: 28, bucket: { kind: 'none' } }], has_more: false });
    await vi.waitFor(() => expect(state.coverage.counts).toEqual({ recognized: 0, other: 28 }));
    await state.next();
    expect(source.coverageQueries).toHaveLength(1);
    source.failure = new Error('offline');
    state.reportRange.setPreset('week');
    await state.run();
    expect(state.page).toBe(2);
    expect(state.coverage.counts).toEqual({ recognized: 0, other: 28 });
    source.failure = undefined;
    source.handler = undefined;
    await state.narrowToSession('selected');
    await vi.waitFor(() => expect(state.coverage.pending).toBe(false));
    expect(source.coverageQueries).toHaveLength(2);
    expect(source.coverageQueries[1].filters).toEqual([{ dimension: 'session_id', values: ['selected'] }]);
    state.dispose();
  });

  it('inspects classifications in the submitted frozen scope without touching either form draft', async (): Promise<void> => {
    const source = new InMemoryLogCounts();
    const state = new AnalyticsState(source, now);
    await state.run();
    await state.narrowToSession('selected');
    const submitted = state.result;
    state.draft.setPreset('week');
    state.draft.selectFilter('source', 'custom draft');
    const customFingerprint = state.draft.fingerprint;
    state.reportRange.setPreset('day');
    const rangeFingerprint = state.reportRange.fingerprint;
    state.setReport('custom');
    await state.inspectClassifications();
    expect(source.reportQueries.at(-1)).toEqual({
      time_range: submitted?.query.time_range,
      filters: [{ dimension: 'session_id', values: ['selected'] }],
      group_by: ['activity_kind', 'source', 'event_name', 'tool_name', 'session_id'],
      bucketing: { kind: 'none' }, pagination: { limit: 100, offset: 0 }
    });
    expect(state.resultLabel).toBe('Log classifications');
    expect(state.report).toBe('logs');
    expect(state.countLabel).toBe('Log records');
    expect(state.changed).toBe(true);
    expect(state.draft.fingerprint).toBe(customFingerprint);
    expect(state.reportRange.fingerprint).toBe(rangeFingerprint);
    expect(source.coverageQueries).toHaveLength(2);
    await state.run();
    expect(state.changed).toBe(false);
    expect(state.narrowedSession).toBeUndefined();
    expect(source.reportQueries.at(-1)?.filters).toEqual([]);
    state.dispose();
  });

  it('treats inspection with unchanged settings as clean and keeps counts for the same scope', async (): Promise<void> => {
    const source = new InMemoryLogCounts();
    const state = new AnalyticsState(source, now);
    await state.run();
    await state.inspectClassifications();
    expect(state.changed).toBe(false);
    expect(state.report).toBe('logs');
    expect(source.coverageQueries).toHaveLength(1);
    state.dispose();
  });

  it('does not count failed first submissions or custom results and keeps auxiliary errors separate', async (): Promise<void> => {
    const source = new InMemoryLogCounts();
    const state = new AnalyticsState(source, now);
    source.failure = new Error('offline');
    await state.run();
    expect(source.coverageQueries).toHaveLength(0);
    expect(state.coverage.counts).toBeUndefined();
    source.failure = undefined;
    source.handler = async (query) => {
      if (isClassificationQuery(query)) throw new Error('count failure');
      return { rows: [], has_more: false };
    };
    await state.run();
    await vi.waitFor(() => expect(state.coverage.error).not.toBe(''));
    expect(state.error).toBe('');
    expect(state.resultLabel).toBe('Tool calls');
    source.handler = undefined;
    await state.coverage.retry();
    expect(state.coverage.counts).toEqual({ recognized: 0, other: 0 });
    state.setReport('custom');
    await state.run();
    expect(state.coverage.counts).toBeUndefined();
    expect(source.coverageQueries).toHaveLength(2);
    const requests = source.queries.length;
    await state.inspectClassifications();
    expect(source.queries).toHaveLength(requests);
    state.dispose();
  });

  it('auxiliary access loss clears primary results and fences a pending primary query', async (): Promise<void> => {
    const source = new InMemoryLogCounts();
    const state = new AnalyticsState(source, now);
    await state.run();
    await vi.waitFor(() => expect(state.coverage.pending).toBe(false));
    let complete!: (value: LogCountResponse) => void;
    source.handler = () => new Promise((resolve) => { complete = resolve; });
    const pending = state.run();
    source.failure = new HttpError(403, 'Forbidden', {});
    await state.coverage.retry();
    expect(state.accessLost).toBe(true);
    expect(state.result).toBeUndefined();
    expect(state.coverage.counts).toBeUndefined();
    expect(source.signals[2]?.aborted).toBe(true);
    complete({ rows: [], has_more: false });
    await pending;
    expect(state.result).toBeUndefined();
    state.dispose();
  });

  it('validates all seven dimensions in filters, grouping and responses', (): void => {
    expect(logCountQuerySchema.safeParse({
      time_range: { start: '2026-10-31T11:00:00Z', end: '2026-10-31T12:00:00Z' },
      filters: dimensions.map((dimension) => ({ dimension, values: ['unsupported'] })),
      group_by: [...dimensions],
      bucketing: { kind: 'none' },
      pagination: { limit: 100, offset: 0 }
    }).success).toBe(true);
    expect(logCountResponseSchema.safeParse({
      rows: [{ groups: dimensions.map((dimension) => ({ dimension, value: { kind: 'missing' } })), count: 1, bucket: { kind: 'none' } }],
      has_more: false
    }).success).toBe(true);
  });
});
