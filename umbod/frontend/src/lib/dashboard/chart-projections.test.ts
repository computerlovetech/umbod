import { describe, expect, it } from 'vitest';
import { projectActivity, projectOutcomes, projectUsage } from './chart-projections';
import { personalUsageSchema, type UsageDays } from './domain/usage-schemas';
import { usageSnapshot } from './usage-fixtures.test-support';

describe('usage chart projections', (): void => {
  it.each([7, 30] as const)('keeps tool outcomes separate from other operations across %i days', (days: UsageDays): void => {
    const snapshot = usageSnapshot(days);
    const counts = {
      tool: { success: 8, failure: 2, cancelled: 10 },
      resource: { success: 40, failure: 30, cancelled: 10 },
      prompt: { success: 2, failure: 3, cancelled: 5 }
    };
    const usage = personalUsageSchema.parse({
      ...snapshot, totals: counts,
      daily: snapshot.daily.map((day, index) => index === 2 ? { ...day, counts } : day)
    });
    const charts = projectUsage(usage);
    expect(charts.outcomes.total).toBe(20);
    expect(charts.outcomes.successRate).toBe('40.0');
    expect(charts.outcomes.segments.map((segment) => segment.percentage)).toEqual([40, 10, 50]);
    expect(charts.outcomes.segments.map((segment) => segment.offset)).toEqual([0, 40, 50]);
    expect(charts.mix.total).toBe(110);
    expect(charts.mix.segments.map((segment) => segment.count)).toEqual([20, 80, 10]);
    expect(charts.mix.segments.map((segment) => segment.share)).toEqual([20 / 110 * 100, 80 / 110 * 100, 10 / 110 * 100]);
    expect(charts.activity.days).toHaveLength(days);
    expect(charts.activity.days[2]).toMatchObject({ success: 8, failure: 2, cancelled: 10, total: 20 });
    expect(charts.activity.total).toBe(20);
    expect(charts.activity.axisMaximum).toBeGreaterThanOrEqual(20);
  });

  it('has honest empty projections before loading and for zero snapshots', (): void => {
    for (const charts of [projectUsage(), projectUsage(usageSnapshot())]) {
      expect(charts.outcomes.label).toBe('No tool calls');
      expect(charts.outcomes.successRate).toBe('');
      expect(charts.outcomes.segments.every((segment) => segment.percentage === 0)).toBe(true);
      expect(charts.mix.total).toBe(0);
      expect(charts.activity.total).toBe(0);
      expect(charts.activity.axisMaximum).toBe(50);
    }
    expect(projectUsage().activity.days).toEqual([]);
    expect(projectUsage(usageSnapshot()).activity.days).toHaveLength(7);
  });

  it('does not imply tool calls when only resources were used', (): void => {
    const snapshot = usageSnapshot();
    const counts = { ...snapshot.totals, resource: { success: 5, failure: 2, cancelled: 3 } };
    const charts = projectUsage(personalUsageSchema.parse({
      ...snapshot, totals: counts,
      daily: snapshot.daily.map((day, index) => index === 0 ? { ...day, counts } : day)
    }));
    expect(charts.outcomes.label).toBe('No tool calls');
    expect(charts.activity.total).toBe(0);
    expect(charts.mix.segments.map((segment) => segment.share)).toEqual([0, 100, 0]);
  });

  it('counts cancelled calls in the denominator even with no successes', (): void => {
    const chart = projectOutcomes({ success: 0, failure: 1, cancelled: 3 });
    expect(chart.successRate).toBe('0.0');
    expect(chart.segments.map((segment) => segment.percentage)).toEqual([0, 25, 75]);
  });

  it('scales the activity axis for large days and retains per-day zeros', (): void => {
    const activity = projectActivity([
      { date: '2026-11-01', success: 0, failure: 0, cancelled: 0 },
      { date: '2026-11-02', success: 300, failure: 25, cancelled: 1 }
    ]);
    expect(activity.axisMaximum).toBe(350);
    expect(activity.days.map((day) => day.total)).toEqual([0, 326]);
    expect(activity.label).toContain('326 tool calls');
  });
});
