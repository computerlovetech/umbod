import { afterEach, describe, expect, it, vi } from 'vitest';
import { flushSync, mount, tick, unmount } from 'svelte';
import AnalyticsWorkspace from './AnalyticsWorkspace.svelte';
import { AnalyticsState } from '$lib/admin/analytics/analytics-state.svelte';
import { InMemoryLogCounts } from '$lib/admin/analytics/in-memory.test-support';
import { HttpError } from '$lib/admin/infrastructure/transport';

let component: ReturnType<typeof mount> | undefined;

afterEach(async (): Promise<void> => {
  if (component) await unmount(component);
  component = undefined;
  document.body.replaceChildren();
});

function button(name: string): HTMLButtonElement {
  const found = [...document.querySelectorAll('button')].find((entry) => entry.getAttribute('aria-label') === name || entry.textContent?.trim() === name);
  if (!found) throw new Error(`Missing button: ${name}`);
  return found;
}

function input(id: string, value: string): void {
  const element = document.getElementById(id) as HTMLInputElement;
  element.value = value;
  element.dispatchEvent(new Event('input', { bubbles: true }));
}

function render(): InMemoryLogCounts {
  const source = new InMemoryLogCounts();
  source.response = { rows: [
    { groups: [{ dimension: 'severity', value: { kind: 'missing' } }], count: 0, bucket: { kind: 'none' } },
    { groups: [{ dimension: 'severity', value: { kind: 'present', value: '' } }], count: 7, bucket: { kind: 'none' } }
  ] };
  const state = new AnalyticsState(source, () => new Date('2026-10-31T12:00:00Z'));
  const target = document.createElement('div');
  document.body.append(target);
  component = mount(AnalyticsWorkspace, { target, props: { state } });
  flushSync();
  return source;
}

describe('analytics query interaction', () => {
  it('adds exact and blank filter values, submits, and keeps result context separate from edits', async (): Promise<void> => {
    const source = render();
    input('analytics-filter-source', ' exact value ');
    button('Add Source value').click();
    await tick();
    button('Add Source value').click();
    await tick();
    button('Run query').click();
    await vi.waitFor(() => expect(document.querySelector('table')).not.toBeNull());
    expect(source.queries[0].filters).toEqual([{ dimension: 'source', values: [' exact value ', ''] }]);
    expect(document.querySelector('tbody')?.textContent).toContain('Missing attribute');
    expect(document.querySelector('tbody')?.textContent).toContain('Empty string');
    expect(document.querySelector('tbody')?.textContent).toContain('0');
    input('analytics-limit', '20');
    await tick();
    expect(document.body.textContent).toContain('Draft changed — run query to apply.');
    expect(document.body.textContent).toContain('Maximum 100 groups');
    expect(source.queries).toHaveLength(1);
  });

  it('provides keyboard-focusable results content with a native link back to the query', async (): Promise<void> => {
    render();
    button('Run query').click();
    await vi.waitFor(() => expect(document.querySelector('.table-scroll a')).not.toBeNull());
    const editQuery = document.querySelector<HTMLAnchorElement>('.table-scroll a');
    expect(editQuery?.tabIndex).toBe(0);
    expect(editQuery?.getAttribute('href')).toBe('#analytics-query');
    expect(document.getElementById('analytics-query')?.tagName).toBe('FORM');
  });

  it('routes checkbox and grouping order actions into the submitted query', async (): Promise<void> => {
    const source = render();
    const sourceCheckbox = [...document.querySelectorAll<HTMLInputElement>('input[type="checkbox"]')].find((field) => field.parentElement?.textContent === 'Source');
    sourceCheckbox?.click();
    await tick();
    button('Move Source earlier').click();
    await tick();
    source.response = { rows: [{ groups: [{ dimension: 'source', value: { kind: 'present', value: 'api' } }, { dimension: 'severity', value: { kind: 'present', value: 'INFO' } }], count: 12, bucket: { kind: 'none' } }] };
    button('Run query').click();
    await vi.waitFor(() => expect(source.queries).toHaveLength(1));
    expect(source.queries[0].group_by).toEqual(['source', 'severity']);
    await vi.waitFor(() => expect([...document.querySelectorAll('tbody td')].map((cell) => cell.textContent)).toEqual(['"api"', '"INFO"', '12']));
  });

  it('requires unadded text to be added and permits retry after service failure', async (): Promise<void> => {
    const source = render();
    input('analytics-filter-tool_name', 'tools.search');
    button('Run query').click();
    await tick();
    expect(document.querySelector('[role="alert"]')?.textContent).toContain('Add or clear');
    expect(source.queries).toHaveLength(0);
    button('Add Tool name value').click();
    source.failure = new HttpError(503, 'Unavailable', {});
    await tick();
    button('Run query').click();
    await vi.waitFor(() => expect(document.querySelector('[role="alert"]')?.textContent).toContain('disabled'));
    source.failure = undefined;
    source.response = { rows: [] };
    button('Retry query').click();
    await vi.waitFor(() => expect(document.body.textContent).toContain('No logs matched this query.'));
    expect(document.querySelector('[role="alert"]')).toBeNull();
  });

  it('submits custom wall times with the chosen offset and ordered bucket selection', async (): Promise<void> => {
    const source = render();
    (document.querySelectorAll('[role="combobox"]')[0] as HTMLButtonElement).click();
    await tick();
    ([...document.querySelectorAll('[role="option"]')].find((entry) => entry.textContent?.includes('Custom range')) as HTMLElement).click();
    await tick();
    input('analytics-start', '2026-10-31T09:00');
    input('analytics-end', '2026-10-31T10:00');
    input('analytics-offset', '-04:00');
    (document.querySelectorAll('[role="combobox"]')[1] as HTMLButtonElement).click();
    await tick();
    ([...document.querySelectorAll('[role="option"]')].find((entry) => entry.textContent?.trim() === 'Day') as HTMLElement).click();
    await tick();
    source.response = { rows: [] };
    button('Run query').click();
    await vi.waitFor(() => expect(source.queries).toHaveLength(1));
    expect(source.queries[0].time_range).toEqual({ start: '2026-10-31T13:00:00.000Z', end: '2026-10-31T14:00:00.000Z' });
    expect(source.queries[0].bucketing).toEqual({ kind: 'fixed', width: 'day' });
  });

  it('removes privileged results and query controls when access is revoked', async (): Promise<void> => {
    const source = render();
    button('Run query').click();
    await vi.waitFor(() => expect(document.querySelector('table')).not.toBeNull());
    source.failure = new HttpError(403, 'Forbidden', {});
    button('Run query').click();
    await vi.waitFor(() => expect(document.querySelector('form')).toBeNull());
    expect(document.querySelector('table')).toBeNull();
    expect(document.querySelector('[role="alert"]')?.textContent).toContain('Administration access');
  });
});
