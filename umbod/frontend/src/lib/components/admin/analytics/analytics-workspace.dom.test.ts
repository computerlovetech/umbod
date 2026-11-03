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

async function chooseObservedValue(label: string): Promise<void> {
  const field = document.querySelector<HTMLInputElement>('input[role="combobox"]');
  field?.focus();
  field?.click();
  await tick();
  const option = [...document.querySelectorAll<HTMLElement>('[role="option"]')].find((entry) => entry.textContent?.includes(label));
  expect(option).toBeDefined();
  option?.click();
  await tick();
}

describe('analytics query interaction', () => {
  it('starts with compact controls and keeps advanced settings and help collapsed', (): void => {
    render();
    expect(document.querySelector('h1')?.textContent).toBe('Log analytics');
    expect(document.querySelector<HTMLDetailsElement>('details.advanced')?.open).toBe(false);
    expect(document.querySelector<HTMLDetailsElement>('details.about')?.open).toBe(false);
    expect(document.querySelector('[aria-label="Add a filter"]')).toBeNull();
    expect(document.querySelectorAll('input[type="text"]')).toHaveLength(0);
    expect(button('+ Add filter').getAttribute('aria-expanded')).toBe('false');
  });

  it('shows validation even when an invalid advanced field is collapsed', async (): Promise<void> => {
    const source = render();
    input('analytics-limit', '0');
    button('Run query').click();
    await tick();
    expect(document.querySelector('[role="alert"]')?.textContent).toContain('whole-number group limit');
    expect(source.queries).toHaveLength(0);
  });

  it('chooses observed values without typing exact matches and keeps submitted results separate from edits', async (): Promise<void> => {
    const source = render();
    source.response = { rows: [
      { groups: [{ dimension: 'source', value: { kind: 'present', value: ' exact value ' } }], count: 3, bucket: { kind: 'none' } },
      { groups: [{ dimension: 'source', value: { kind: 'present', value: '' } }], count: 4, bucket: { kind: 'none' } }
    ] };
    button('+ Add filter').click();
    await vi.waitFor(() => expect(document.querySelector<HTMLInputElement>('input[role="combobox"]')?.disabled).toBe(false));
    await chooseObservedValue('exact value');
    await chooseObservedValue('Empty value');
    expect(document.querySelector('[aria-label="Selected filters"]')?.textContent).toContain('Source:');
    source.response = { rows: [
      { groups: [{ dimension: 'severity', value: { kind: 'missing' } }], count: 0, bucket: { kind: 'none' } },
      { groups: [{ dimension: 'severity', value: { kind: 'present', value: '' } }], count: 7, bucket: { kind: 'none' } }
    ] };
    button('Run query').click();
    await vi.waitFor(() => expect(document.querySelector('table')).not.toBeNull());
    expect(source.queries[1].filters).toEqual([{ dimension: 'source', values: [' exact value ', ''] }]);
    expect(document.querySelector('tbody')?.textContent).toContain('Missing attribute');
    expect(document.querySelector('tbody')?.textContent).toContain('Empty string');
    expect(document.querySelector('tbody')?.textContent).toContain('0');
    input('analytics-limit', '20');
    await tick();
    expect(document.body.textContent).toContain('Filters or settings changed. Run query to update results.');
    expect(document.body.textContent).toContain('Maximum 100 groups');
    expect(source.queries).toHaveLength(2);
    button('Remove Source value " exact value "').click();
    await tick();
    expect(document.querySelector('[aria-label="Selected filters"]')?.textContent).not.toContain('exact value');
  });

  it('searches and selects observed values with the keyboard', async (): Promise<void> => {
    const source = render();
    source.response = { rows: [
      { groups: [{ dimension: 'source', value: { kind: 'present', value: 'worker' } }], count: 2, bucket: { kind: 'none' } },
      { groups: [{ dimension: 'source', value: { kind: 'present', value: 'api' } }], count: 3, bucket: { kind: 'none' } }
    ] };
    button('+ Add filter').click();
    await vi.waitFor(() => expect(document.querySelector<HTMLInputElement>('input[role="combobox"]')?.disabled).toBe(false));
    const field = document.querySelector<HTMLInputElement>('input[role="combobox"]')!;
    field.focus();
    field.value = 'WORK';
    field.dispatchEvent(new Event('input', { bubbles: true }));
    await tick();
    expect([...document.querySelectorAll('[role="option"]')].map((option) => option.textContent?.trim())).toEqual(['worker (2)']);
    field.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
    await tick();
    expect(document.querySelector('[aria-label="Selected filters"]')?.textContent).toContain('worker');
    expect(source.queries).toHaveLength(1);
  });

  it('shows recoverable value-loading failures without submitting the main query', async (): Promise<void> => {
    const source = render();
    source.failure = new HttpError(422, 'Too many groups', {});
    button('+ Add filter').click();
    await vi.waitFor(() => expect(document.querySelector('[role="alert"]')?.textContent).toContain('narrower time range'));
    expect(document.querySelector('table')).toBeNull();
    source.failure = undefined;
    source.response = { rows: [] };
    button('Retry values').click();
    await vi.waitFor(() => expect(document.querySelector('[role="alert"]')).toBeNull());
    const field = document.querySelector<HTMLInputElement>('input[role="combobox"]')!;
    field.focus();
    await tick();
    expect(document.body.textContent).toContain('No unselected values in this time range.');
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
    await vi.waitFor(() => expect([...document.querySelectorAll('tbody td')].map((cell) => cell.textContent)).toEqual(['api', 'INFO', '12']));
  });

  it('permits retry after service failure', async (): Promise<void> => {
    const source = render();
    source.failure = new HttpError(503, 'Unavailable', {});
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
