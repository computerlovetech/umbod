import { usageSummarySchema, type UsageDays, type UsageSummary } from '#lib/usage/usage-schemas.js';

export function usageSummaryFixture(days: UsageDays = 7, successes = 0): UsageSummary {
  const end = Date.parse('2026-11-10');
  const counts = {
    tool: { success: successes, failure: 0, cancelled: 0 },
    resource: { success: 0, failure: 0, cancelled: 0 },
    prompt: { success: 0, failure: 0, cancelled: 0 }
  };
  return usageSummarySchema.parse({
    top_tools: [],
    as_of: '2026-11-09T12:00:00Z',
    range: { start: new Date(end - days * 86400000).toISOString().slice(0, 10), end: '2026-11-10', timezone: 'UTC' },
    totals: { ...counts, tool: { ...counts.tool, success: successes * days } },
    daily: Array.from({ length: days }, (_, index) => ({
      date: new Date(end - (days - index) * 86400000).toISOString().slice(0, 10), counts
    }))
  });
}

export function deferred<T>(): { promise: Promise<T>; resolve: (value: T) => void; reject: (reason: unknown) => void } {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((complete, fail): void => { resolve = complete; reject = fail; });
  return { promise, resolve, reject };
}
