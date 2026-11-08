import { describe, expect, it } from 'vitest';
import { ActivityCoverage } from './activity-coverage.svelte';
import { InMemoryLogCounts } from './in-memory.test-support';
import { resolveReport } from './reports';
import type { LogCountResponse } from './domain/schemas';
import { AuthenticationRequiredError, HttpError } from '../infrastructure/transport';

const range = { start: '2026-10-31T11:00:00Z', end: '2026-10-31T12:00:00Z' };
const query = resolveReport('tools', range);

function classified(value: string | undefined, count: number): LogCountResponse['rows'][number] {
  return { groups: [{ dimension: 'activity_kind', value: value === undefined ? { kind: 'missing' } : { kind: 'present', value } }], bucket: { kind: 'none' }, count };
}

function deferred(): { promise: Promise<LogCountResponse>; resolve: (value: LogCountResponse) => void } {
  let resolve!: (value: LogCountResponse) => void;
  const promise = new Promise<LogCountResponse>((complete) => { resolve = complete; });
  return { promise, resolve };
}

describe('scope classification counts', () => {
  it('freezes the submitted range and non-activity filters, reads all pages and uses latest duplicate counts', async (): Promise<void> => {
    const source = new InMemoryLogCounts();
    const coverage = new ActivityCoverage(source, () => {});
    const second = deferred();
    source.handler = async (request) => request.pagination.offset === 0
      ? { rows: [classified('tool_call', 3), classified(undefined, 18), classified('', 2)], has_more: true }
      : second.promise;
    const submitted = { ...query, filters: [...query.filters, { dimension: 'session_id' as const, values: [' exact session '] }, { dimension: 'source' as const, values: ['worker'] }] };
    const loading = coverage.load(submitted);
    submitted.filters[1].values.push('later draft');
    await Promise.resolve();
    await Promise.resolve();
    expect(coverage.counts).toBeUndefined();
    second.resolve({ rows: [classified('tool_call', 5), classified('skill_activation', 4), classified('other_activity', 6)], has_more: false });
    await loading;
    expect(source.queries).toEqual([0, 1000].map((offset) => ({
      time_range: range, filters: [{ dimension: 'session_id', values: [' exact session '] }, { dimension: 'source', values: ['worker'] }],
      group_by: ['activity_kind'], bucketing: { kind: 'none' }, pagination: { limit: 1000, offset }
    })));
    expect(coverage.counts).toEqual({ recognized: 15, other: 20 });
    expect(coverage.pending).toBe(false);
    expect(coverage.error).toBe('');
  });

  it('does not publish partial totals and independently retries the frozen scope', async (): Promise<void> => {
    const source = new InMemoryLogCounts();
    const coverage = new ActivityCoverage(source, () => {});
    source.handler = async (request) => {
      if (request.pagination.offset) throw new Error('offline');
      return { rows: [classified(undefined, 28)], has_more: true };
    };
    await coverage.load(query);
    expect(coverage.counts).toBeUndefined();
    expect(coverage.error).not.toBe('');
    source.handler = undefined;
    source.classificationResponse = { rows: [classified(undefined, 28)], has_more: false };
    await coverage.retry();
    expect(coverage.counts).toEqual({ recognized: 0, other: 28 });
    expect(source.queries[2]).toEqual(source.queries[0]);
  });

  it.each([
    { rows: [{ groups: [], bucket: { kind: 'none' }, count: 1 }], has_more: false },
    { rows: [{ groups: [{ dimension: 'source', value: { kind: 'missing' } }], bucket: { kind: 'none' }, count: 1 }], has_more: false },
    { rows: [{ ...classified('tool_call', 1), bucket: { kind: 'bucket', start: range.start } }], has_more: false }
  ] satisfies LogCountResponse[])('reports malformed aggregate shapes as unavailable rather than zero', async (response): Promise<void> => {
    const source = new InMemoryLogCounts();
    source.classificationResponse = response;
    const coverage = new ActivityCoverage(source, () => {});
    await coverage.load(query);
    expect(coverage.counts).toBeUndefined();
    expect(coverage.error).not.toBe('');
  });

  it('reuses identical time and scope regardless of report, paging or filter order and refreshes changed scope', async (): Promise<void> => {
    const source = new InMemoryLogCounts();
    const coverage = new ActivityCoverage(source, () => {});
    await coverage.load(query);
    await coverage.load({ ...resolveReport('files', range), pagination: { limit: 100, offset: 100 } });
    expect(source.queries).toHaveLength(1);
    await coverage.load({ ...query, filters: [...query.filters, { dimension: 'session_id', values: ['selected'] }] });
    expect(source.queries).toHaveLength(2);
    await coverage.load({ ...query, time_range: { ...range, start: '2026-10-30T11:00:00Z' } });
    expect(source.queries).toHaveLength(3);
  });

  it('aborts changed scopes and fences out-of-order completion and disposal', async (): Promise<void> => {
    const source = new InMemoryLogCounts();
    const coverage = new ActivityCoverage(source, () => {});
    const first = deferred();
    source.handler = () => first.promise;
    const old = coverage.load(query);
    source.handler = undefined;
    source.classificationResponse = { rows: [classified('tool_call', 2)], has_more: false };
    await coverage.load({ ...query, filters: [{ dimension: 'session_id', values: ['new'] }] });
    expect(source.signals[0]?.aborted).toBe(true);
    first.resolve({ rows: [classified(undefined, 99)], has_more: false });
    await old;
    expect(coverage.counts).toEqual({ recognized: 2, other: 0 });
    const last = deferred();
    source.handler = () => last.promise;
    const pending = coverage.retry();
    coverage.dispose();
    expect(source.signals[2]?.aborted).toBe(true);
    last.resolve({ rows: [classified(undefined, 99)], has_more: false });
    await pending;
    await coverage.load(query);
    await coverage.retry();
    expect(source.queries).toHaveLength(3);
    expect(coverage.counts).toBeUndefined();
    expect(coverage.pending).toBe(false);
  });

  it.each([new AuthenticationRequiredError(), new HttpError(401, 'Unauthorized', {}), new HttpError(403, 'Forbidden', {})])('clears counts and invokes the explicit access-loss callback', async (failure): Promise<void> => {
    const source = new InMemoryLogCounts();
    let accessLost = false;
    const coverage = new ActivityCoverage(source, () => { accessLost = true; });
    await coverage.load(query);
    source.failure = failure;
    await coverage.retry();
    expect(accessLost).toBe(true);
    expect(coverage.counts).toBeUndefined();
    expect(coverage.pending).toBe(false);
  });
});
