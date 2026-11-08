import { describe, expect, it } from 'vitest';
import { AnalyticsState } from './analytics-state.svelte';
import { InMemoryLogCounts } from './in-memory.test-support';
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
    expect(source.queries).toHaveLength(0);
    await state.run();
    expect(source.queries[0]).toEqual({
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
    expect(source.queries[0].filters).toEqual([{ dimension: 'activity_kind', values: ['tool_call', 'file_read', 'file_edit'] }]);
    state.setReport('custom');
    state.draft.setPreset('week');
    state.draft.setBucket('day');
    state.draft.selectFilter('outcome', 'unsupported');
    state.draft.toggleGroup('activity_kind');
    await state.run();
    const custom = source.queries[1];
    state.setReport('files');
    state.reportRange.setPreset('day');
    await state.run();
    state.setReport('custom');
    await state.run();
    expect(source.queries[3]).toEqual(custom);
    state.dispose();
  });

  it('freezes submitted report metadata, query and absolute range through navigation and retry', async (): Promise<void> => {
    const source = new InMemoryLogCounts();
    source.response = { rows: [], has_more: true };
    const state = new AnalyticsState(source, now);
    await state.run();
    const submitted = source.queries[0];
    state.setReport('custom');
    state.draft.setPreset('week');
    source.failure = new Error('offline');
    await state.next();
    expect(state.resultLabel).toBe('Tool calls');
    expect(state.countLabel).toBe('Reported tool calls');
    source.failure = undefined;
    state.setReport('skills');
    await state.retry();
    expect(source.queries[2]).toEqual({ ...submitted, pagination: { limit: 100, offset: 100 } });
    expect(state.result?.report).toBe('tools');
    expect(state.changed).toBe(true);
    expect(state.page).toBe(2);
    await state.previous();
    expect(source.queries[3]).toEqual(submitted);
    state.dispose();
  });

  it.each(['tools', 'files', 'skills'])('drills into %s results and returns to all sessions using the frozen submitted query', async (report): Promise<void> => {
    const source = new InMemoryLogCounts();
    source.response = { rows: [], has_more: true };
    const state = new AnalyticsState(source, now);
    state.setReport(report);
    await state.run();
    const submitted = source.queries[0];
    await state.next();
    state.setReport('custom');
    state.draft.setPreset('week');
    state.draft.selectFilter('session_id', 'custom draft');
    state.reportRange.setPreset('custom');
    state.reportRange.setStart('invalid');
    await state.narrowToSession(' exact session ');
    const narrowed = { ...submitted, filters: [...submitted.filters, { dimension: 'session_id', values: [' exact session '] }], pagination: { limit: 100, offset: 0 } };
    expect(source.queries[2]).toEqual(narrowed);
    expect(state.result?.report).toBe(report);
    expect(state.narrowedSession).toBe(' exact session ');
    expect(state.page).toBe(1);
    expect(state.changed).toBe(true);
    await state.next();
    expect(source.queries[3]).toEqual({ ...narrowed, pagination: { limit: 100, offset: 100 } });
    await state.allSessions();
    expect(source.queries[4]).toEqual(submitted);
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
    const failedQuery = source.queries[source.queries.length - 1];
    expect(state.result).toBe(previous);
    expect(state.error).not.toBe('');
    state.setReport('skills');
    state.reportRange.setPreset('week');
    source.failure = undefined;
    await state.retry();
    expect(source.queries[source.queries.length - 1]).toEqual(failedQuery);
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
    source.handler = () => new Promise((resolve) => { complete = resolve; });
    const pending = state.narrowToSession('selected');
    await state.narrowToSession('other');
    await state.allSessions();
    await state.next();
    expect(source.queries).toHaveLength(2);
    expect(state.pending).toBe(true);
    source.handler = undefined;
    state.setReport('files');
    await state.run();
    expect(source.signals[1]?.aborted).toBe(true);
    complete({ rows: [], has_more: false });
    await pending;
    expect(state.result?.report).toBe('files');
    expect(state.narrowedSession).toBeUndefined();
    state.dispose();
    await state.narrowToSession('ignored');
    await state.allSessions();
    expect(source.queries).toHaveLength(3);
  });

  it('keeps custom session filtering separate and starts fresh standard runs across all sessions', async (): Promise<void> => {
    const source = new InMemoryLogCounts();
    const state = new AnalyticsState(source, now);
    await state.narrowToSession('ignored');
    await state.allSessions();
    expect(source.queries).toHaveLength(0);
    state.setReport('custom');
    state.draft.selectFilter('session_id', 'manual');
    await state.run();
    await state.narrowToSession('ignored');
    await state.allSessions();
    expect(source.queries).toHaveLength(1);
    expect(state.narrowedSession).toBeUndefined();
    expect(source.queries[0].filters).toEqual([{ dimension: 'session_id', values: ['manual'] }]);
    state.setReport('tools');
    await state.run();
    await state.narrowToSession('selected');
    await state.narrowToSession('');
    expect(state.narrowedSession).toBe('selected');
    await state.run();
    expect(state.narrowedSession).toBeUndefined();
    expect(source.queries[3].filters).toEqual([{ dimension: 'activity_kind', values: ['tool_call', 'file_read', 'file_edit'] }]);
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
    source.handler = () => new Promise((resolve) => { complete = resolve; });
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
    expect(source.queries).toHaveLength(2);
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
