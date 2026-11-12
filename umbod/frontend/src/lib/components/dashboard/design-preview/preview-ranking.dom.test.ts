import { afterEach, describe, expect, it } from 'vitest';
import { flushSync, mount, unmount } from 'svelte';
import DashboardPreview from './DashboardPreview.svelte';

let component: ReturnType<typeof mount> | undefined;

afterEach(async (): Promise<void> => {
  if (component) await unmount(component);
  component = undefined;
  document.body.replaceChildren();
});

function connectorCheckbox(name: string): HTMLInputElement {
  const label = Array.from(document.querySelectorAll('label')).find((candidate): boolean => candidate.textContent?.trim() === name);
  const checkbox = label?.querySelector('input');
  expect(checkbox).toBeInstanceOf(HTMLInputElement);
  return checkbox!;
}

function rankedRows(): readonly string[] {
  return Array.from(document.querySelectorAll('.tool-ranking li')).map((row): string => row.textContent ?? '');
}

function button(label: string): HTMLButtonElement {
  const found = Array.from(document.querySelectorAll('button')).find((candidate): boolean => candidate.textContent === label);
  expect(found).toBeDefined();
  return found!;
}

describe('preview tool ranking', (): void => {
  it('compares static empty shapes with sample data through the preview controls', (): void => {
    component = mount(DashboardPreview, { target: document.body });
    flushSync();
    connectorCheckbox('Slack').click();
    button('30 days').click();
    flushSync();
    const sampleRows = rankedRows();
    button('Empty state').click();
    flushSync();

    expect(button('Empty state').getAttribute('aria-pressed')).toBe('true');
    expect(button('Sample data').getAttribute('aria-pressed')).toBe('false');
    expect(button('30 days').getAttribute('aria-pressed')).toBe('true');
    expect(document.body.textContent).toContain('Preview · empty state');
    expect(document.querySelectorAll('.dashboard-panel')).toHaveLength(4);
    expect(document.querySelector('svg[aria-label="No tool calls"]')).not.toBeNull();
    expect(document.querySelector('svg text')).toBeNull();
    expect(document.querySelector('[aria-label="No operations"]')).not.toBeNull();
    expect(document.querySelector('.dv-plot')).not.toBeNull();
    expect(document.querySelectorAll('.dv-bar')).toHaveLength(0);
    expect(document.querySelectorAll('.empty-ranking-row')).toHaveLength(5);
    expect(document.querySelector('[role="img"][aria-label="No per-tool usage data"]')).not.toBeNull();
    expect(document.querySelector('.empty-ranking [aria-hidden="true"]')).not.toBeNull();
    expect(document.querySelector('[aria-busy="true"]')).toBeNull();
    expect(rankedRows()).toEqual([]);
    expect(document.querySelectorAll('.connector-filter input')).toHaveLength(0);
    expect(document.body.textContent).not.toMatch(/No usage yet|No tool calls|No operations|0 calls|Select all connectors|search|fetch_page/);
    expect(Array.from(document.querySelectorAll('.dv-outcome-legend dd, .dv-mix-legend dd')).every((node): boolean => node.textContent === '')).toBe(true);

    button('7 days').click();
    flushSync();
    expect(document.querySelectorAll('.empty-ranking-row')).toHaveLength(5);
    button('30 days').click();
    button('Sample data').click();
    flushSync();
    expect(rankedRows()).toEqual(sampleRows);
    expect(document.querySelectorAll('.empty-ranking-row')).toHaveLength(0);
    expect(connectorCheckbox('Slack').checked).toBe(false);
  });
  it('updates the visible ranking through connector checkboxes and period controls', (): void => {
    component = mount(DashboardPreview, { target: document.body });
    flushSync();
    expect(rankedRows()).toHaveLength(5);
    expect(rankedRows()[0]).toContain('277');

    connectorCheckbox('Slack').click();
    flushSync();
    expect(rankedRows()).toHaveLength(5);
    expect(rankedRows().every((row): boolean => !row.includes('Slack'))).toBe(true);
    expect(rankedRows().some((row): boolean => row.includes('Notion'))).toBe(true);

    const monthButton = Array.from(document.querySelectorAll('button')).find((button): boolean => button.textContent === '30 days');
    expect(monthButton).toBeDefined();
    monthButton!.click();
    flushSync();
    expect(rankedRows()[0]).toContain('1,197');
    expect(connectorCheckbox('Slack').checked).toBe(false);

    connectorCheckbox('GitHub').click();
    connectorCheckbox('Notion').click();
    flushSync();
    expect(rankedRows()).toEqual([]);
    expect(document.querySelectorAll('.empty-ranking-row')).toHaveLength(5);
    expect(document.body.textContent).not.toContain('No connectors selected');
    expect(document.querySelector('[aria-label="Most-used tools"]')).not.toBeNull();
    const restore = Array.from(document.querySelectorAll('button')).find((button): boolean => button.textContent === 'Select all connectors');
    expect(restore).toBeDefined();
    restore!.click();
    flushSync();
    expect(rankedRows()).toHaveLength(5);
    expect(connectorCheckbox('Slack').checked).toBe(true);
  });
});
