import { afterEach, describe, expect, it, vi } from 'vitest';
import { flushSync, mount, tick, unmount } from 'svelte';
import AnalyticsWorkspace from './AnalyticsWorkspace.svelte';
import { AnalyticsState } from '$lib/admin/analytics/analytics-state.svelte';
import { InMemoryLogCounts, isClassificationQuery } from '$lib/admin/analytics/in-memory.test-support';
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
  source.response = { has_more: false, rows: [
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
  expect(field).not.toBeNull();
  field!.focus();
  field!.click();
  await tick();
  const option = [...document.querySelectorAll<HTMLElement>('[role="option"]')].find((entry) => entry.textContent?.includes(label));
  expect(option).toBeDefined();
  option!.click();
  await tick();
}

async function select(label: string, optionLabel: string): Promise<void> {
  const labelElement = [...document.querySelectorAll('label')].find((entry) => entry.textContent === label);
  expect(labelElement).toBeDefined();
  const field = document.getElementById(labelElement!.htmlFor);
  expect(field).not.toBeNull();
  field!.click();
  await tick();
  const option = [...document.querySelectorAll<HTMLElement>('[role="option"]')].find((entry) => entry.querySelector('span')?.textContent?.trim() === optionLabel);
  expect(option).toBeDefined();
  option!.click();
  await tick();
}

async function renderCustom(): Promise<InMemoryLogCounts> {
  const source = render();
  await select('Report', 'Custom log query');
  return source;
}

describe('analytics reports interaction', () => {
  it('shows scope-wide classifications for empty activity results and inspects the frozen session without losing custom edits', async (): Promise<void> => {
    const source = render();
    source.classificationResponse = { rows: [{ groups: [{ dimension: 'activity_kind', value: { kind: 'missing' } }], count: 28, bucket: { kind: 'none' } }], has_more: false };
    source.response = { rows: [{ groups: [{ dimension: 'session_id', value: { kind: 'present', value: 'selected' } }], count: 2, bucket: { kind: 'none' } }], has_more: false };
    button('Run report').click();
    await vi.waitFor(() => expect(document.querySelector('[aria-label="Scope log classifications"]')?.textContent).toContain('28'));
    source.response = { rows: [], has_more: false };
    button('View session selected').click();
    await vi.waitFor(() => expect(document.body.textContent).toContain('There are stored logs in this scope'));
    const submitted = source.reportQueries[1];
    await select('Report', 'Custom log query');
    await select('Time range', 'Last 7 days');
    await select('Report', 'Tool calls');
    await select('Time range', 'Last 24 hours');
    source.response = { rows: [
      { groups: [{ dimension: 'activity_kind', value: { kind: 'missing' } }], count: 18, bucket: { kind: 'none' } },
      { groups: [{ dimension: 'activity_kind', value: { kind: 'present', value: '' } }], count: 10, bucket: { kind: 'none' } }
    ], has_more: false };
    button('Inspect log classifications').click();
    await vi.waitFor(() => expect(document.querySelector('h2')?.textContent).toBe('Log classifications'));
    expect([...document.querySelectorAll('button')].map((entry) => entry.textContent?.trim())).not.toContain('Inspect log classifications');
    expect(source.reportQueries[2]).toMatchObject({ time_range: submitted.time_range, filters: [{ dimension: 'session_id', values: ['selected'] }], pagination: { limit: 100, offset: 0 }, group_by: ['activity_kind', 'source', 'event_name', 'tool_name', 'session_id'] });
    expect(document.querySelector('tbody')?.textContent).toContain('Unclassified');
    expect(document.querySelector('dt')?.textContent).toBe('Log records on this page');
    expect(document.body.textContent).toContain('Report settings changed');
    expect(source.coverageQueries).toHaveLength(2);
    await select('Report', 'Custom log query');
    expect(document.body.textContent).toContain('Last 7 days');
    button('Run query').click();
    await vi.waitFor(() => expect(document.querySelector('h2')?.textContent).toBe('Results'));
    expect(document.querySelector('[aria-label="Scope log classifications"]')).toBeNull();
    expect(document.body.textContent).not.toContain('Inspect log classifications');
  });

  it('keeps report results usable during count failure and retries only counts', async (): Promise<void> => {
    const source = render();
    source.handler = async (query) => {
      if (isClassificationQuery(query)) throw new Error('offline');
      return source.response;
    };
    button('Run report').click();
    await vi.waitFor(() => expect(document.body.textContent).toContain('Log classification counts could not be loaded'));
    expect(document.querySelector('table')).not.toBeNull();
    expect([...document.querySelectorAll('button')].map((entry) => entry.textContent?.trim())).not.toContain('Retry query');
    source.handler = undefined;
    button('Retry counts').click();
    await vi.waitFor(() => expect(document.querySelector('[aria-label="Scope log classifications"] [role="alert"]')).toBeNull());
    expect(source.reportQueries).toHaveLength(1);
    expect(source.coverageQueries).toHaveLength(2);
  });
  it.each([
    ['Tool calls', ['tool_call', 'file_read', 'file_edit'], ['source', 'session_id', 'outcome'], 'Reported tool calls'],
    ['File activity', ['file_read', 'file_edit'], ['source', 'session_id', 'activity_kind'], 'Read/edit-tool calls'],
    ['Skill activity', ['skill_activation'], ['source', 'session_id'], 'Skill activations']
  ])('runs %s across all sessions only on submit with page-scoped counts', async (report, activities, groups, countLabel): Promise<void> => {
    const source = render();
    await select('Report', report);
    await select('Time range', 'Last 24 hours');
    expect(document.getElementById('analytics-session')).toBeNull();
    expect(source.reportQueries).toHaveLength(0);
    expect(document.querySelector('fieldset')).toBeNull();
    source.response = { has_more: false, rows: [] };
    button('Run report').click();
    await vi.waitFor(() => expect(document.querySelector('h2')?.textContent).toBe(report));
    expect(source.reportQueries[0]).toMatchObject({
      filters: [{ dimension: 'activity_kind', values: activities }],
      group_by: groups, bucketing: { kind: 'none' },
      time_range: { start: '2026-10-30T12:00:00.000Z', end: '2026-10-31T12:00:00.000Z' }
    });
    expect(document.querySelector('dt')?.textContent).toBe(countLabel + ' on this page');
    expect(document.querySelector('.submitted-filters')).toBeNull();
    expect(document.body.textContent).toContain('All sessions');
    expect(document.body.textContent).not.toContain('Activity kind:');
    expect(document.body.textContent).toContain('Result rows on this page');
    expect(document.body.textContent).toContain('No reported matching activity');
    expect(document.body.textContent).toContain('does not establish zero usage or telemetry coverage');
    if (report === 'File activity') {
      expect(document.body.textContent).toContain('not unique files');
      expect(document.body.textContent).toContain('Excludes shell and implicit reads');
    }
    if (report === 'Skill activity') expect(document.body.textContent).toContain('not unique skills');
  });

  it('renders one row per group with honest missing and unknown outcome labels', async (): Promise<void> => {
    const source = render();
    source.response = { has_more: false, rows: [
      { groups: [{ dimension: 'source', value: { kind: 'missing' } }, { dimension: 'session_id', value: { kind: 'missing' } }, { dimension: 'outcome', value: { kind: 'missing' } }], count: 2, bucket: { kind: 'none' } },
      ...['success', 'failure', 'unknown'].map((value) => ({
        groups: [{ dimension: 'source' as const, value: { kind: 'present' as const, value: 'client' } }, { dimension: 'session_id' as const, value: { kind: 'present' as const, value: 'session' } }, { dimension: 'outcome' as const, value: { kind: 'present' as const, value } }],
        count: 1, bucket: { kind: 'none' as const }
      }))
    ] };
    button('Run report').click();
    await vi.waitFor(() => expect(document.querySelectorAll('tbody tr')).toHaveLength(4));
    expect([...document.querySelectorAll('tbody tr:first-child td')].map((cell) => cell.textContent)).toEqual(['Not reported', 'Not reported', 'Not reported', '2']);
    expect(document.querySelector('tbody')?.textContent).toContain('Successful');
    expect(document.querySelector('tbody')?.textContent).toContain('Failed');
    expect(document.querySelector('tbody')?.textContent).toContain('Unknown outcome');
    expect(document.querySelector('dd')?.textContent).toBe('5');
    expect(document.querySelector('caption')?.textContent).toContain('Edit report');
    expect(document.querySelector('caption')?.textContent).toContain('A session can have multiple rows or span pages.');
    expect(document.querySelector('caption')?.textContent).not.toContain('No time buckets');
  });

  it('labels read/edit calls without pivoting source and session groups', async (): Promise<void> => {
    const source = render();
    await select('Report', 'File activity');
    source.response = { has_more: false, rows: ['file_read', 'file_edit'].map((value) => ({
      groups: [{ dimension: 'source', value: { kind: 'present', value: 'client' } }, { dimension: 'session_id', value: { kind: 'present', value: 'session' } }, { dimension: 'activity_kind', value: { kind: 'present', value } }],
      count: 3, bucket: { kind: 'none' }
    })) };
    button('Run report').click();
    await vi.waitFor(() => expect(document.querySelectorAll('tbody tr')).toHaveLength(2));
    expect(document.querySelector('tbody')?.textContent).toContain('Read-tool calls');
    expect(document.querySelector('tbody')?.textContent).toContain('Edit-tool calls');
  });

  it('drills into a result session and returns to all sessions without entering an ID', async (): Promise<void> => {
    const source = render();
    source.response = { has_more: true, rows: [{ groups: [{ dimension: 'session_id', value: { kind: 'present', value: ' exact session ' } }], count: 3, bucket: { kind: 'none' } }] };
    button('Run report').click();
    await vi.waitFor(() => expect(document.querySelector('table')).not.toBeNull());
    const submitted = source.reportQueries[0];
    button('Next').click();
    await vi.waitFor(() => expect(document.querySelector('nav')?.textContent).toContain('Page 2'));
    await select('Report', 'Custom log query');
    await select('Time range', 'Last 7 days');
    let complete!: (response: typeof source.response) => void;
    source.handler = (query) => isClassificationQuery(query) ? Promise.resolve(source.classificationResponse) : new Promise((resolve) => { complete = resolve; });
    button('View session  exact session ').click();
    await tick();
    expect(button('View session  exact session ').disabled).toBe(true);
    expect(button('Previous').disabled).toBe(true);
    expect(button('Next').disabled).toBe(true);
    complete({ has_more: false, rows: [] });
    await vi.waitFor(() => expect(document.querySelector('.submitted-filters')?.textContent).toBe('Session ID:  exact session '));
    expect(source.reportQueries[2]).toEqual({ ...submitted, filters: [...submitted.filters, { dimension: 'session_id', values: [' exact session '] }] });
    expect(document.querySelector('h2')?.textContent).toBe('Tool calls');
    expect(document.querySelector('nav')?.textContent).toContain('Page 1');
    expect(document.body.textContent).toContain('No reported matching activity');
    source.handler = undefined;
    button('All sessions').click();
    await vi.waitFor(() => expect(document.querySelector('.submitted-filters')).toBeNull());
    expect(source.reportQueries[3]).toEqual(submitted);
    expect(document.body.textContent).toContain('Last 7 days');
    expect(document.querySelector('h2')?.textContent).toBe('Tool calls');
    expect(document.querySelector('nav')?.textContent).toContain('Page 1');
  });

  it('does not offer drill-down for missing or empty IDs or submitted custom queries', async (): Promise<void> => {
    const source = render();
    source.response = { has_more: false, rows: [
      { groups: [{ dimension: 'session_id', value: { kind: 'missing' } }], count: 1, bucket: { kind: 'none' } },
      { groups: [{ dimension: 'session_id', value: { kind: 'present', value: '' } }], count: 1, bucket: { kind: 'none' } },
      { groups: [{ dimension: 'session_id', value: { kind: 'present', value: 'available' } }], count: 1, bucket: { kind: 'none' } }
    ] };
    button('Run report').click();
    await vi.waitFor(() => expect(document.querySelectorAll('tbody tr')).toHaveLength(3));
    expect(document.querySelectorAll('tbody button')).toHaveLength(1);
    expect(button('View session available')).toBeDefined();
    expect(document.querySelector('tbody tr:first-child button')).toBeNull();
    expect(document.querySelector('tbody tr:nth-child(2) button')).toBeNull();
    await select('Report', 'Custom log query');
    expect(button('View session available')).toBeDefined();
    button('Run query').click();
    await vi.waitFor(() => expect(document.querySelector('h2')?.textContent).toBe('Results'));
    expect(document.querySelectorAll('tbody button')).toHaveLength(0);
    expect(document.body.textContent).not.toContain('All sessions');
  });

  it('adds exact session filters manually only inside the custom filter picker', async (): Promise<void> => {
    const source = await renderCustom();
    source.response = { has_more: false, rows: [] };
    expect(document.getElementById('analytics-session')).toBeNull();
    button('+ Add filter').click();
    await vi.waitFor(() => expect(document.querySelector<HTMLInputElement>('input[role="combobox"]')?.disabled).toBe(false));
    await select('Filter by', 'Session ID');
    await vi.waitFor(() => expect(button('Add session filter').disabled).toBe(true));
    input('analytics-session', ' exact session ');
    await tick();
    button('Add session filter').click();
    await tick();
    expect(document.querySelector('[aria-label="Selected filters"]')?.textContent).toContain('Session ID:  exact session ');
    expect(button('Add session filter').disabled).toBe(true);
    button('Run query').click();
    await vi.waitFor(() => expect(document.querySelector('h2')?.textContent).toBe('Results'));
    expect(source.reportQueries[2].filters).toEqual([{ dimension: 'session_id', values: [' exact session '] }]);
    await select('Report', 'Tool calls');
    expect(document.getElementById('analytics-session')).toBeNull();
    button('Run report').click();
    await vi.waitFor(() => expect(document.querySelector('h2')?.textContent).toBe('Tool calls'));
    expect(source.reportQueries[3].filters).toEqual([{ dimension: 'activity_kind', values: ['tool_call', 'file_read', 'file_edit'] }]);
  });

  it('retains custom interval, range and grouping across report draft changes', async (): Promise<void> => {
    const source = await renderCustom();
    await select('Interval', 'Day');
    await select('Time range', 'Last 7 days');
    const checkbox = [...document.querySelectorAll<HTMLInputElement>('input[type="checkbox"]')].find((field) => field.parentElement?.textContent === 'Outcome');
    expect(checkbox).toBeDefined();
    checkbox!.click();
    await tick();
    await select('Report', 'File activity');
    await select('Time range', 'Last 24 hours');
    await select('Report', 'Custom log query');
    expect(document.body.textContent).toContain('Last 7 days');
    button('Run query').click();
    await vi.waitFor(() => expect(source.reportQueries).toHaveLength(1));
    expect(source.reportQueries[0]).toMatchObject({
      group_by: ['severity', 'outcome'], filters: [], bucketing: { kind: 'fixed', width: 'day' },
      time_range: { start: '2026-10-24T12:00:00.000Z', end: '2026-10-31T12:00:00.000Z' }
    });
  });

  it('keeps submitted report labels and range during custom draft navigation and retry', async (): Promise<void> => {
    const source = render();
    source.response = { has_more: true, rows: [{ groups: [{ dimension: 'outcome', value: { kind: 'present', value: 'unknown' } }], count: 4, bucket: { kind: 'none' } }] };
    button('Run report').click();
    await vi.waitFor(() => expect(document.querySelector('table')).not.toBeNull());
    const submitted = source.reportQueries[0];
    await select('Report', 'Custom log query');
    await select('Time range', 'Last 7 days');
    source.failure = new Error('offline');
    button('Next').click();
    await vi.waitFor(() => expect(document.querySelector('[role="alert"]')).not.toBeNull());
    expect(document.querySelector('h2')?.textContent).toBe('Tool calls');
    expect(document.querySelector('tbody')?.textContent).toContain('Unknown outcome');
    await select('Report', 'Skill activity');
    source.failure = undefined;
    button('Retry query').click();
    await vi.waitFor(() => expect(document.querySelector('nav')?.textContent).toContain('Page 2'));
    expect(source.reportQueries[2]).toEqual({ ...submitted, pagination: { limit: 100, offset: 100 } });
    expect(document.querySelector('h2')?.textContent).toBe('Tool calls');
    expect(document.querySelector('dt')?.textContent).toBe('Reported tool calls on this page');
    expect(document.querySelector('tbody')?.textContent).toContain('Unknown outcome');
    button('Previous').click();
    await vi.waitFor(() => expect(source.reportQueries).toHaveLength(4));
    expect(source.reportQueries[3]).toEqual(submitted);
  });

  it('removes report controls and results on access loss', async (): Promise<void> => {
    const source = render();
    button('Run report').click();
    await vi.waitFor(() => expect(document.querySelector('table')).not.toBeNull());
    source.failure = new HttpError(403, 'Forbidden', {});
    button('Run report').click();
    await vi.waitFor(() => expect(document.querySelector('form')).toBeNull());
    expect(document.querySelector('table')).toBeNull();
    expect(document.querySelector('[role="alert"]')?.textContent).toContain('Administration access');
  });
});

describe('analytics query interaction', () => {
  it('navigates server pages, preserves draft edits and retries the failed page', async (): Promise<void> => {
    const source = await renderCustom();
    source.response = { ...source.response, has_more: true };
    button('Run query').click();
    await vi.waitFor(() => expect(document.querySelector('table')).not.toBeNull());
    expect(button('Previous').disabled).toBe(true);
    expect(button('Next').disabled).toBe(false);
    const checkbox = document.querySelector<HTMLInputElement>('input[type="checkbox"]');
    expect(checkbox).not.toBeNull();
    checkbox!.click();
    await tick();
    let complete!: (response: typeof source.response) => void;
    source.handler = (query) => isClassificationQuery(query) ? Promise.resolve(source.classificationResponse) : new Promise((resolve) => { complete = resolve; });
    button('Next').click();
    await tick();
    expect(button('Next').disabled).toBe(true);
    expect(button('Previous').disabled).toBe(true);
    expect(source.queries[1]).toEqual({ ...source.queries[0], pagination: { limit: 100, offset: 100 } });
    complete({ rows: [{ groups: [{ dimension: 'severity', value: { kind: 'present', value: 'page two' } }], count: 2, bucket: { kind: 'none' } }], has_more: false });
    await vi.waitFor(() => expect(document.querySelector('tbody')?.textContent).toContain('page two'));
    expect(document.querySelector('nav[aria-label="Results pagination"]')?.textContent).toContain('Page 2');
    expect(button('Next').disabled).toBe(true);
    expect(button('Previous').disabled).toBe(false);
    expect(checkbox!.checked).toBe(true);
    expect(document.body.textContent).toContain('Filters or settings changed');
    source.handler = undefined;
    source.failure = new Error('offline');
    button('Previous').click();
    await vi.waitFor(() => expect(document.querySelector('[role="alert"]')).not.toBeNull());
    expect(document.querySelector('tbody')?.textContent).toContain('page two');
    source.failure = undefined;
    source.response = { rows: [], has_more: true };
    button('Retry query').click();
    await vi.waitFor(() => expect(document.querySelector('nav[aria-label="Results pagination"]')?.textContent).toContain('Page 1'));
    expect(source.queries[3]).toEqual(source.queries[2]);
    expect(button('Previous').disabled).toBe(true);
    button('Run query').click();
    await vi.waitFor(() => expect(source.queries).toHaveLength(5));
    expect(source.queries[4].pagination).toEqual({ limit: 100, offset: 0 });
    expect(source.queries[4].group_by).toEqual(['severity', 'source']);
  });

  it('starts with compact controls without advanced settings or help sections', (): void => {
    render();
    expect(document.querySelector('h1')?.textContent).toBe('Log analytics');
    expect(document.querySelector('details')).toBeNull();
    expect(document.body.textContent).not.toContain('Advanced');
    expect(document.body.textContent).not.toContain('About these logs');
    expect(document.getElementById('analytics-limit')).toBeNull();
    expect(document.querySelector('[aria-label="Add a filter"]')).toBeNull();
    expect(document.querySelectorAll('input[type="text"]')).toHaveLength(0);
    expect(document.getElementById('analytics-session')).toBeNull();
    expect(document.querySelector('fieldset')).toBeNull();
    expect(document.body.textContent).not.toContain('Interval');
    expect(button('Run report')).toBeDefined();
    expect(document.body.textContent).not.toContain('Session ID');
  });

  it('chooses observed values without typing exact matches and keeps submitted results separate from edits', async (): Promise<void> => {
    const source = await renderCustom();
    source.response = { has_more: false, rows: [
      { groups: [{ dimension: 'source', value: { kind: 'present', value: ' exact value ' } }], count: 3, bucket: { kind: 'none' } },
      { groups: [{ dimension: 'source', value: { kind: 'present', value: '' } }], count: 4, bucket: { kind: 'none' } }
    ] };
    button('+ Add filter').click();
    await vi.waitFor(() => expect(document.querySelector<HTMLInputElement>('input[role="combobox"]')?.disabled).toBe(false));
    await chooseObservedValue('exact value');
    await chooseObservedValue('Empty value');
    expect(document.querySelector('[aria-label="Selected filters"]')?.textContent).toContain('Source:');
    source.response = { has_more: false, rows: [
      { groups: [{ dimension: 'severity', value: { kind: 'missing' } }], count: 0, bucket: { kind: 'none' } },
      { groups: [{ dimension: 'severity', value: { kind: 'present', value: '' } }], count: 7, bucket: { kind: 'none' } }
    ] };
    button('Run query').click();
    await vi.waitFor(() => expect(document.querySelector('table')).not.toBeNull());
    expect(source.queries[1].filters).toEqual([{ dimension: 'source', values: [' exact value ', ''] }]);
    expect(document.querySelector('tbody')?.textContent).toContain('Missing attribute');
    expect(document.querySelector('tbody')?.textContent).toContain('Empty string');
    expect(document.querySelector('tbody')?.textContent).toContain('0');
    button('Remove Source value ""').click();
    await tick();
    expect(document.body.textContent).toContain('Filters or settings changed. Run query to update results.');
    expect(document.body.textContent).toContain('Logs on this page');
    expect(source.queries).toHaveLength(2);
    button('Remove Source value " exact value "').click();
    await tick();
    expect(document.querySelector('[aria-label="Selected filters"]')?.textContent).not.toContain('exact value');
  });

  it('searches and selects observed values with the keyboard', async (): Promise<void> => {
    const source = await renderCustom();
    source.response = { has_more: false, rows: [
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
    const source = await renderCustom();
    source.failure = new HttpError(422, 'Invalid query', {});
    button('+ Add filter').click();
    await vi.waitFor(() => expect(document.querySelector('[role="alert"]')?.textContent).toContain('query settings'));
    expect(document.querySelector('table')).toBeNull();
    source.failure = undefined;
    source.response = { has_more: false, rows: [] };
    button('Retry values').click();
    await vi.waitFor(() => expect(document.querySelector('[role="alert"]')).toBeNull());
    const field = document.querySelector<HTMLInputElement>('input[role="combobox"]')!;
    field.focus();
    await tick();
    expect(document.body.textContent).toContain('No unselected values in this time range.');
  });

  it('provides keyboard-focusable results content with a native link back to the query', async (): Promise<void> => {
    await renderCustom();
    button('Run query').click();
    await vi.waitFor(() => expect(document.querySelector('.table-scroll a')).not.toBeNull());
    const editQuery = document.querySelector<HTMLAnchorElement>('.table-scroll a');
    expect(editQuery?.tabIndex).toBe(0);
    expect(editQuery?.getAttribute('href')).toBe('#analytics-query');
    expect(document.getElementById('analytics-query')?.tagName).toBe('FORM');
  });

  it('uses checkbox selection order as the submitted grouping order', async (): Promise<void> => {
    const source = await renderCustom();
    const sourceCheckbox = [...document.querySelectorAll<HTMLInputElement>('input[type="checkbox"]')].find((field) => field.parentElement?.textContent === 'Source');
    expect(sourceCheckbox).toBeDefined();
    sourceCheckbox!.click();
    await tick();
    source.response = { has_more: false, rows: [{ groups: [{ dimension: 'severity', value: { kind: 'present', value: 'INFO' } }, { dimension: 'source', value: { kind: 'present', value: 'api' } }], count: 12, bucket: { kind: 'none' } }] };
    button('Run query').click();
    await vi.waitFor(() => expect(source.queries).toHaveLength(1));
    expect(source.queries[0].group_by).toEqual(['severity', 'source']);
    await vi.waitFor(() => expect([...document.querySelectorAll('tbody td')].map((cell) => cell.textContent)).toEqual(['INFO', 'api', '12']));
  });

  it('permits retry after service failure', async (): Promise<void> => {
    const source = await renderCustom();
    source.failure = new HttpError(503, 'Unavailable', {});
    button('Run query').click();
    await vi.waitFor(() => expect(document.querySelector('[role="alert"]')?.textContent).toContain('disabled'));
    source.failure = undefined;
    source.response = { has_more: false, rows: [] };
    button('Retry query').click();
    await vi.waitFor(() => expect(document.body.textContent).toContain('No logs on this page.'));
    expect(document.querySelector('[role="alert"]')).toBeNull();
  });

  it('submits custom wall times with the chosen offset and ordered bucket selection', async (): Promise<void> => {
    const source = await renderCustom();
    await select('Time range', 'Custom range');
    input('analytics-start', '2026-10-31T09:00');
    input('analytics-end', '2026-10-31T10:00');
    input('analytics-offset', '-04:00');
    await select('Interval', 'Day');
    source.response = { has_more: false, rows: [] };
    button('Run query').click();
    await vi.waitFor(() => expect(source.queries).toHaveLength(1));
    expect(source.queries[0].time_range).toEqual({ start: '2026-10-31T13:00:00.000Z', end: '2026-10-31T14:00:00.000Z' });
    expect(source.queries[0].bucketing).toEqual({ kind: 'fixed', width: 'day' });
  });

  it('removes privileged results and query controls when access is revoked', async (): Promise<void> => {
    const source = await renderCustom();
    button('Run query').click();
    await vi.waitFor(() => expect(document.querySelector('table')).not.toBeNull());
    source.failure = new HttpError(403, 'Forbidden', {});
    button('Run query').click();
    await vi.waitFor(() => expect(document.querySelector('form')).toBeNull());
    expect(document.querySelector('table')).toBeNull();
    expect(document.querySelector('[role="alert"]')?.textContent).toContain('Administration access');
  });
});
