import { describe, expect, it } from 'vitest';
import { DashboardPreviewState } from './preview-state.svelte';

describe('Dashboard design preview', (): void => {
  it.each([7, 30] as const)('keeps %i dated empty buckets without sample tools or invented chart values', (period): void => {
    const state = new DashboardPreviewState();
    state.setPeriod(period);
    const dates = state.days.map((day): string => day.date);
    state.setScenario('empty');

    expect(state.scenario).toBe('empty');
    expect(state.days.map((day): string => day.date)).toEqual(dates);
    expect(state.totals).toEqual({ success: 0, failure: 0, cancelled: 0, all: 0 });
    expect(state.activityChart.days).toHaveLength(period);
    expect(state.activityChart.days.every((day): boolean => day.total === 0)).toBe(true);
    expect(state.activityChart.axisMaximum).toBe(50);
    expect(state.outcomeChart.total).toBe(0);
    expect(state.outcomeChart.successRate).toBe('');
    expect(state.outcomeChart.segments.every((segment): boolean => segment.count === 0 && segment.percentage === 0)).toBe(true);
    expect(state.operationChart.total).toBe(0);
    expect(state.operationChart.segments.every((segment): boolean => segment.count === 0 && segment.share === 0)).toBe(true);
    expect(state.topTools).toEqual([]);
  });

  it('restores sample data without losing period or connector selection across empty previews', (): void => {
    const state = new DashboardPreviewState();
    state.setConnectorSelected('Slack', false);
    state.setPeriod(30);
    const ranking = state.topTools;
    const totals = state.totals;

    state.setScenario('empty');
    state.setPeriod(7);
    expect(state.activityChart.days).toHaveLength(7);
    expect(state.topTools).toEqual([]);
    state.setPeriod(30);
    state.setScenario('sample');

    expect(state.period).toBe(30);
    expect(state.selectedConnectors).toEqual(['GitHub', 'Notion']);
    expect(state.topTools).toEqual(ranking);
    expect(state.totals).toEqual(totals);
  });
  it('keeps successful, failed and cancelled tool calls distinct in the ratio', (): void => {
    const state = new DashboardPreviewState();
    const { success, failure, cancelled, all } = state.totals;

    expect(success).toBeGreaterThan(0);
    expect(failure).toBeGreaterThan(0);
    expect(cancelled).toBeGreaterThan(0);
    expect(all).toBe(success + failure + cancelled);
    expect(state.outcomeChart.segments.map((outcome) => outcome.count)).toEqual([success, failure, cancelled]);
    expect(state.outcomeChart.segments.reduce((sum, outcome): number => sum + outcome.percentage, 0)).toBeCloseTo(100);
    expect(state.outcomeChart.successRate).toBe((success / all * 100).toFixed(1));
  });

  it('ranks the top five by count and keeps identically named tools distinct by connector', (): void => {
    const state = new DashboardPreviewState();

    expect(state.topTools).toHaveLength(5);
    expect(state.topTools.map((tool) => tool.count)).toEqual([277, 196, 147, 117, 98]);
    expect(state.topTools.slice(0, 2).map((tool) => [tool.name, tool.connector])).toEqual([
      ['search', 'GitHub'], ['search', 'Slack']
    ]);
    expect(state.topTools[0].barWidth).toBe(100);
  });

  it('filters across multiple selected connectors before taking the top five', (): void => {
    const state = new DashboardPreviewState();
    state.setConnectorSelected('Slack', false);

    expect(state.topTools.map((tool) => tool.connector)).toEqual(['GitHub', 'Notion', 'GitHub', 'GitHub', 'Notion']);
    state.setConnectorSelected('Notion', false);
    expect(state.topTools.map((tool) => tool.name)).toEqual(['search', 'list_issues', 'get_pull_request']);
    state.setConnectorSelected('Slack', true);
    expect(state.topTools).toHaveLength(5);
    expect(state.topTools.some((tool) => tool.connector === 'Notion')).toBe(false);
    state.setConnectorSelected('Slack', true);
    expect(state.selectedConnectors).toEqual(['GitHub', 'Slack']);
  });

  it.each([7, 30] as const)('reconciles per-tool counts with the tool call total over %i days', (period): void => {
    const state = new DashboardPreviewState();
    state.setPeriod(period);
    const tools = state.connectors.flatMap((connector) => {
      for (const name of state.connectors) state.setConnectorSelected(name, name === connector);
      return state.topTools;
    });

    expect(tools).toHaveLength(8);
    expect(new Set(tools.map((tool) => tool.id)).size).toBe(8);
    expect(tools.reduce((sum, tool): number => sum + tool.count, 0)).toBe(state.totals.all);
  });

  it('shows no tools when all connectors are deselected and can restore all', (): void => {
    const state = new DashboardPreviewState();
    for (const connector of state.connectors) state.setConnectorSelected(connector, false);

    expect(state.topTools).toEqual([]);
    state.selectAllConnectors();
    expect(state.topTools).toHaveLength(5);
  });

  it('updates ranked counts with the period without discarding connector selection', (): void => {
    const state = new DashboardPreviewState();
    state.setConnectorSelected('Slack', false);
    const weekCount = state.topTools[0].count;
    state.setPeriod(30);

    expect(state.topTools[0].count).toBeGreaterThan(weekCount);
    expect(state.selectedConnectors).toEqual(['GitHub', 'Notion']);
    state.setPeriod(7);
    expect(state.topTools[0].count).toBe(weekCount);
  });

  it('changes the activity and outcome charts together when the period changes', (): void => {
    const state = new DashboardPreviewState();
    const weekTotal = state.totals.all;

    expect(state.activityChart.days).toHaveLength(7);
    state.setPeriod(30);
    expect(state.period).toBe(30);
    expect(state.activityChart.days).toHaveLength(30);
    expect(state.totals.all).toBeGreaterThan(weekTotal);
    expect(state.activityChart.days.reduce((sum, day): number => sum + day.total, 0)).toBe(state.totals.all);
    expect(state.activityChart.axisMaximum).toBeGreaterThanOrEqual(Math.max(...state.activityChart.days.map((day): number => day.total)));
    state.setPeriod(7);
    expect(state.totals.all).toBe(weekTotal);
  });
});
