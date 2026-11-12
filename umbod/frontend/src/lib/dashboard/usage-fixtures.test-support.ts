import { personalUsageSchema, type PersonalUsage, type UsageDays } from './domain/usage-schemas';

export function usageSnapshot(days: UsageDays = 7, identity = 'account-one', successes = 0): PersonalUsage {
  const end = Date.parse('2026-11-10');
  const counts = {
    tool: { success: successes, failure: 0, cancelled: 0 },
    resource: { success: 0, failure: 0, cancelled: 0 },
    prompt: { success: 0, failure: 0, cancelled: 0 }
  };
  return personalUsageSchema.parse({
    identity_key: identity,
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
