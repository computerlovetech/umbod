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

  test('requires explicit top tools without assuming complete historical coverage', (): void => {
    const snapshot = usageSnapshot(7, 'account-one', 10);
    const { top_tools, ...missingRanking } = snapshot;
    expect(top_tools).toEqual([]);
    expect(personalUsageSchema.safeParse(missingRanking).success).toBe(false);
    const tools = Array.from({ length: 5 }, (_, index) => ({
      tool_id: index.toString(16).padStart(64, '0'), tool_name: 'Search', connector_name: 'Archive', count: 1
    }));
    expect(personalUsageSchema.parse({ ...snapshot, top_tools: tools }).top_tools).toEqual(tools);
    expect(personalUsageSchema.safeParse({ ...snapshot, top_tools: [...tools, { ...tools[0], tool_id: 'f'.repeat(64) }] }).success).toBe(false);
    expect(personalUsageSchema.safeParse({ ...snapshot, top_tools: [tools[0], tools[0]] }).success).toBe(false);
  });

  test.each([
    { tool_id: 'a'.repeat(63) },
    { tool_id: 'a'.repeat(65) },
    { tool_id: 'A'.repeat(64) },
    { tool_id: 'g'.repeat(64) },
    { tool_name: '' },
    { connector_name: '' },
    { count: 0 },
    { count: -1 },
    { count: 1.5 },
    { count: '1' },
    { extra: true }
  ])('rejects malformed tool rows %j', (invalid): void => {
    const tool = { tool_id: 'a'.repeat(64), tool_name: 'Search', connector_name: 'Archive', count: 1 };
    expect(personalUsageSchema.safeParse({ ...usageSnapshot(), top_tools: [{ ...tool, ...invalid }] }).success).toBe(false);
  });

  test.each([null, {}, [{ tool_id: 'a'.repeat(64) }]])('rejects malformed rankings %j', (top_tools): void => {
    expect(personalUsageSchema.safeParse({ ...usageSnapshot(), top_tools }).success).toBe(false);
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
