import { describe, expect, test } from 'vitest';
import { usageSnapshot } from '../usage-fixtures.test-support';
import { personalUsageSchema, usageDaysSchema } from './usage-schemas';

describe('usage snapshot contract', () => {
  test.each([7, 30] as const)('accepts %s complete UTC dates including today with zero counts', (days): void => {
    const snapshot = usageSnapshot(days);
    expect(personalUsageSchema.parse(snapshot)).toEqual(snapshot);
    expect(snapshot.daily).toHaveLength(days);
    expect(snapshot.daily.at(-1)?.date).toBe('2026-11-09');
  });

  test.each([
    { totals: { tool: { success: -1, failure: 0, cancelled: 0 } } },
    { identity_key: '' },
    { as_of: '2026-11-09T12:00:00+02:00' },
    { owner: 'someone' },
    { range: { start: '2026-11-03', end: '2026-11-10', timezone: 'local' } },
    { daily: [] }
  ])('rejects malformed snapshots %j', (invalid): void => {
    expect(personalUsageSchema.safeParse({ ...usageSnapshot(), ...invalid }).success).toBe(false);
  });

  test('accepts an explicit UTC timestamp offset', (): void => {
    expect(personalUsageSchema.safeParse({ ...usageSnapshot(), as_of: '2026-11-09T12:00:00+00:00' }).success).toBe(true);
  });

  test('rejects duplicated or missing dates and mismatched sums', (): void => {
    const snapshot = usageSnapshot();
    expect(personalUsageSchema.safeParse({ ...snapshot, daily: snapshot.daily.map(() => snapshot.daily[0]) }).success).toBe(false);
    expect(personalUsageSchema.safeParse({ ...snapshot, totals: usageSnapshot(7, 'account-one', 1).totals }).success).toBe(false);
    expect(usageDaysSchema.safeParse(14).success).toBe(false);
  });
});
