import { afterEach, describe, expect, it } from 'vitest';
import { flushSync, mount, unmount } from 'svelte';
import OutcomeRing from './OutcomeRing.svelte';
import OperationMixChart from './OperationMixChart.svelte';
import DailyActivityChart from './DailyActivityChart.svelte';
import ToolRankingList from './ToolRankingList.svelte';
import type { ActivityChart, OperationChart, OutcomeChart, RankedTool } from './types';
import { VisualizationProps } from './visualization-props.test-support.svelte';

let component: ReturnType<typeof mount> | undefined;

afterEach(async (): Promise<void> => {
  if (component) await unmount(component);
  component = undefined;
  document.body.replaceChildren();
});

describe('neutral dashboard visualizations', (): void => {
  it('updates the labelled ring and renders zero without an implied percentage', (): void => {
    const props = new VisualizationProps<OutcomeChart>({
      total: 4, successRate: '50.0', label: '2 successful, 1 failed, 1 cancelled tool calls',
      segments: [
        { key: 'success', label: 'Successful', count: 2, percentage: 50, offset: 0 },
        { key: 'failure', label: 'Failed', count: 1, percentage: 25, offset: 50 },
        { key: 'cancelled', label: 'Cancelled', count: 1, percentage: 25, offset: 75 }
      ]
    });
    component = mount(OutcomeRing, { target: document.body, props: { get data(): OutcomeChart { return props.value; } } });
    flushSync();
    expect(document.querySelector('svg')?.getAttribute('aria-label')).toContain('1 cancelled');
    expect(document.body.textContent).toContain('50.0');
    expect(document.body.textContent).toContain('Cancelled');
    props.replace({ total: 0, successRate: '', label: 'No tool calls', segments: props.value.segments.map((segment) => ({ ...segment, count: 0, percentage: 0, offset: 0 })) });
    flushSync();
    expect(document.querySelector('svg')?.getAttribute('aria-label')).toBe('No tool calls');
    expect(document.querySelector('svg text')).toBeNull();
    expect(document.body.textContent).not.toContain('No tool calls');
    expect(document.querySelectorAll('.dv-outcome-legend dt')).toHaveLength(3);
    expect(Array.from(document.querySelectorAll('dd')).every((value) => value.textContent === '')).toBe(true);
    expect(document.body.textContent).not.toMatch(/NaN|Infinity|%/);
  });

  it('updates operation counts and labels without assuming fixed category shares', (): void => {
    const props = new VisualizationProps<OperationChart>({
      total: 4, label: 'Tools: 1 (25%), Resources: 3 (75%)',
      segments: [
        { key: 'tool', label: 'Tools', count: 1, share: 25 },
        { key: 'resource', label: 'Resources', count: 3, share: 75 }
      ]
    });
    component = mount(OperationMixChart, { target: document.body, props: { get data(): OperationChart { return props.value; } } });
    flushSync();
    expect(document.querySelector('[role="img"]')?.getAttribute('aria-label')).toContain('Resources: 3 (75%)');
    expect(document.body.textContent).toContain('75.0%');
    props.replace({ total: 0, label: 'No operations', segments: props.value.segments.map((segment) => ({ ...segment, count: 0, share: 0 })) });
    flushSync();
    expect(document.querySelector('[role="img"]')?.getAttribute('aria-label')).toBe('No operations');
    expect(document.body.textContent).not.toContain('No operations');
    expect(document.querySelector('.dv-mix-bar')).not.toBeNull();
    expect(document.querySelectorAll('.dv-mix-legend dt')).toHaveLength(2);
    expect(Array.from(document.querySelectorAll('dd')).every((value) => value.textContent === '')).toBe(true);
    expect(document.body.textContent).not.toMatch(/NaN|Infinity/);
  });

  it('exposes each day and outcome and replaces activity when props change', (): void => {
    const props = new VisualizationProps<ActivityChart>({
      axisMaximum: 50, total: 9, label: '9 tool calls in total. UTC.',
      days: [{ date: '2026-11-01', label: 'Nov 1', success: 6, failure: 2, cancelled: 1, total: 9 }]
    });
    component = mount(DailyActivityChart, { target: document.body, props: { get data(): ActivityChart { return props.value; } } });
    flushSync();
    expect(document.querySelector('[role="group"]')?.getAttribute('aria-label')).toBe('9 tool calls in total. UTC.');
    expect(document.querySelector('[role="img"]')?.getAttribute('aria-label')).toBe('2026-11-01: 6 successful, 2 failed, 1 cancelled tool calls');
    props.replace({ axisMaximum: 1, total: 0, label: 'No tool calls', days: [] });
    flushSync();
    expect(document.querySelectorAll('[role="img"]')).toHaveLength(0);
    expect(document.body.textContent).not.toContain('No tool calls in this period');
    expect(document.querySelector('.dv-plot')).not.toBeNull();
    expect(document.body.innerHTML).not.toMatch(/NaN|Infinity/);
  });

  it('shows the daily breakdown on hover, follows days and dismisses on leaving the plot', (): void => {
    const data: ActivityChart = {
      axisMaximum: 50, total: 74, label: '74 tool calls in total. UTC.',
      days: [
        { date: '2026-11-15', label: 'Nov 15', success: 28, failure: 4, cancelled: 0, total: 32 },
        { date: '2026-11-17', label: 'Nov 17', success: 41, failure: 1, cancelled: 0, total: 42 },
        { date: '2026-11-18', label: 'Nov 18', success: 0, failure: 0, cancelled: 0, total: 0 }
      ]
    };
    component = mount(DailyActivityChart, { target: document.body, props: { data } });
    flushSync();
    const buttons = document.querySelectorAll('button');
    expect(buttons).toHaveLength(3);
    expect(document.querySelector('[role="tooltip"]')).toBeNull();
    expect(document.querySelector('[title]')).toBeNull();
    buttons[0].dispatchEvent(new PointerEvent('pointerenter'));
    flushSync();
    const tooltip = document.querySelector('[role="tooltip"]');
    expect(tooltip?.textContent).toContain('Nov 15, 2026');
    expect(tooltip?.textContent).toContain('UTC');
    expect(Array.from(tooltip?.querySelectorAll('dt') ?? [], (cell) => cell.textContent)).toEqual(['Successful', 'Failed', 'Cancelled']);
    expect(Array.from(tooltip?.querySelectorAll('dd') ?? [], (cell) => cell.textContent)).toEqual(['28', '4', '0']);
    expect(tooltip?.querySelector('.dv-tooltip-total')?.textContent).toBe('Total calls32');
    expect(buttons[0].getAttribute('aria-describedby')).toBe(tooltip?.id);
    expect(buttons[0].classList.contains('dv-day-active')).toBe(true);
    buttons[1].dispatchEvent(new PointerEvent('pointerenter'));
    flushSync();
    expect(document.querySelector('[role="tooltip"]')?.textContent).toContain('Nov 17, 2026');
    expect(document.querySelector('.dv-tooltip-total')?.textContent).toBe('Total calls42');
    expect(buttons[0].classList.contains('dv-day-active')).toBe(false);
    buttons[2].dispatchEvent(new PointerEvent('pointerenter'));
    flushSync();
    expect(document.querySelector('.dv-tooltip-total')?.textContent).toBe('Total calls0');
    expect(Array.from(document.querySelectorAll('.dv-tooltip-values dd'), (cell) => cell.textContent)).toEqual(['0', '0', '0']);
    const plot = document.querySelector('.dv-plot');
    expect(plot).not.toBeNull();
    plot!.dispatchEvent(new PointerEvent('pointerleave'));
    flushSync();
    expect(document.querySelector('[role="tooltip"]')).toBeNull();
    expect(document.querySelector('.dv-day-active')).toBeNull();
  });

  it('prioritizes new keyboard focus over a previous pointer hover', (): void => {
    const data: ActivityChart = {
      axisMaximum: 50, total: 74, label: '74 tool calls in total. UTC.',
      days: [
        { date: '2026-11-15', label: 'Nov 15', success: 28, failure: 4, cancelled: 0, total: 32 },
        { date: '2026-11-17', label: 'Nov 17', success: 41, failure: 1, cancelled: 0, total: 42 }
      ]
    };
    component = mount(DailyActivityChart, { target: document.body, props: { data } });
    flushSync();
    const buttons = document.querySelectorAll('button');
    expect(buttons).toHaveLength(2);
    buttons[0].dispatchEvent(new PointerEvent('pointerenter'));
    flushSync();
    expect(document.querySelector('.dv-tooltip-total')?.textContent).toBe('Total calls32');
    buttons[1].focus();
    flushSync();
    const tooltip = document.querySelector('[role="tooltip"]');
    expect(tooltip?.textContent).toContain('Nov 17, 2026');
    expect(buttons[1].getAttribute('aria-describedby')).toBe(tooltip?.id);
    expect(buttons[0].hasAttribute('aria-describedby')).toBe(false);
    const plot = document.querySelector('.dv-plot');
    expect(plot).not.toBeNull();
    plot!.dispatchEvent(new PointerEvent('pointerleave'));
    flushSync();
    expect(document.querySelector('.dv-tooltip-total')?.textContent).toBe('Total calls42');
  });

  it('supports keyboard focus, Escape, blur and current data without stale tooltip values', (): void => {
    const props = new VisualizationProps<ActivityChart>({
      axisMaximum: 50, total: 32, label: '32 tool calls in total. UTC.',
      days: [{ date: '2026-11-15', label: 'Nov 15', success: 28, failure: 4, cancelled: 0, total: 32 }]
    });
    component = mount(DailyActivityChart, { target: document.body, props: { get data(): ActivityChart { return props.value; } } });
    flushSync();
    const button = document.querySelector('button');
    expect(button).not.toBeNull();
    button!.focus();
    flushSync();
    expect(document.querySelector('[role="tooltip"]')).not.toBeNull();
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    flushSync();
    expect(document.querySelector('[role="tooltip"]')).toBeNull();
    expect(document.activeElement).toBe(button);
    button!.blur();
    button!.focus();
    flushSync();
    expect(document.querySelector('[role="tooltip"]')).not.toBeNull();
    props.replace({ ...props.value, total: 33, days: [{ ...props.value.days[0], success: 29, total: 33 }] });
    flushSync();
    expect(document.querySelector('.dv-tooltip-values dd')?.textContent).toBe('29');
    expect(document.querySelector('.dv-tooltip-total')?.textContent).toBe('Total calls33');
    button!.blur();
    flushSync();
    expect(document.querySelector('[role="tooltip"]')).toBeNull();
    button!.focus();
    flushSync();
    props.replace({ ...props.value, total: 0, days: [] });
    flushSync();
    expect(document.querySelector('[role="tooltip"]')).toBeNull();
    expect(document.querySelector('button')).toBeNull();
  });

  it('keeps tool identities, connectors and counts visible and updates entries', (): void => {
    const props = new VisualizationProps<readonly RankedTool[]>([
      { id: 'one', name: 'search', connector: 'First', count: 12, barWidth: 100 },
      { id: 'two', name: 'search', connector: 'Second', count: 3, barWidth: 25 }
    ]);
    component = mount(ToolRankingList, { target: document.body, props: {
      get tools(): readonly RankedTool[] { return props.value; }
    } });
    flushSync();
    const list = document.querySelector('[aria-label="Top tools by call count"]');
    expect(list?.querySelectorAll('li')).toHaveLength(2);
    expect(list?.textContent).toContain('First');
    expect(list?.textContent).toContain('Second');
    expect(list?.textContent).toContain('12 calls');
    props.replace([]);
    flushSync();
    expect(document.querySelector('ol')).toBeNull();
    expect(document.querySelector('[role="img"][aria-label="No per-tool usage data"]')).not.toBeNull();
    expect(document.querySelectorAll('.empty-ranking-row')).toHaveLength(5);
    expect(document.querySelector('.empty-ranking [aria-hidden="true"]')).not.toBeNull();
    expect(document.querySelector('[aria-busy="true"]')).toBeNull();
    expect(document.body.textContent).not.toMatch(/First|Second|search|calls|No per-tool usage data/);

    props.replace([{ id: 'three', name: 'fetch', connector: 'Third', count: 8, barWidth: 100 }]);
    flushSync();
    expect(document.querySelectorAll('.empty-ranking-row')).toHaveLength(0);
    expect(document.querySelectorAll('.tool-ranking li')).toHaveLength(1);
    expect(document.body.textContent).toContain('Third');
    expect(document.body.textContent).toContain('8 calls');
  });
});
