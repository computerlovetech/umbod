import { afterEach, describe, expect, it, vi } from 'vitest';
import { flushSync, mount, tick, unmount } from 'svelte';
import AnalyticsWorkspace from '#lib/components/shared/analytics/AnalyticsWorkspace.svelte';
import { AnalyticsState } from '#lib/admin/analytics/analytics-state.svelte.js';
import { InMemoryLogCounts } from '#lib/admin/analytics/in-memory.test-support.js';
import type { LogCountResponse } from '#lib/admin/analytics/domain/schemas.js';
import { HttpError } from '#lib/admin/infrastructure/transport.js';

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
  const element = document.getElementById(id);
  expect(element).toBeInstanceOf(HTMLInputElement);
  const field = element as HTMLInputElement;
  field.value = value;
  field.dispatchEvent(new Event('input', { bubbles: true }));
}

function queryTrigger(): HTMLButtonElement {
  const trigger = document.querySelector<HTMLButtonElement>('.query-panel button[aria-controls]');
  if (!trigger) throw new Error('Query trigger not found');
  return trigger;
}

function queryExpanded(): boolean {
  return queryTrigger().getAttribute('aria-expanded') === 'true';
}

async function openQuery(): Promise<void> {
  queryTrigger().click();
  await tick();
  expect(queryExpanded()).toBe(true);
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

function render(source: InMemoryLogCounts = new InMemoryLogCounts(), onAccessLost: () => void = () => {}): InMemoryLogCounts {
  const state = new AnalyticsState(source, () => new Date('2026-10-31T12:00:00Z'), onAccessLost);
  const target = document.createElement('div');
  document.body.append(target);
  component = mount(AnalyticsWorkspace, { target, props: { state } });
  flushSync();
  return source;
}

async function ready(source: InMemoryLogCounts = new InMemoryLogCounts()): Promise<InMemoryLogCounts> {
  render(source);
  await vi.waitFor(() => expect(document.querySelector('[aria-label="Query results"]')).not.toBeNull());
  await tick();
  return source;
}

function sessionSource(): InMemoryLogCounts {
  const source = new InMemoryLogCounts();
  source.response = { has_more: true, rows: [{ groups: [{ dimension: 'session_id', value: { kind: 'present', value: ' exact session ' } }], count: 3, bucket: { kind: 'none' } }] };
  return source;
}

describe('analytics query workspace', () => {
  it('shows initial query progress outside the collapsed editor until results arrive', async (): Promise<void> => {
    const source = new InMemoryLogCounts();
    let complete!: (response: LogCountResponse) => void;
    source.handler = (): Promise<LogCountResponse> => new Promise((resolve): void => { complete = resolve; });
    render(source);
    expect(queryExpanded()).toBe(false);
    const status = [...document.querySelectorAll('[role="status"]')].find((entry): boolean => !entry.closest('.query-panel') && entry.textContent === 'Running query…');
    expect(status).toBeDefined();
    expect(document.querySelector('[aria-label="Query results"]')).toBeNull();
    complete({ rows: [], has_more: false });
    await vi.waitFor((): void => expect(document.querySelector('[aria-label="Query results"]')).not.toBeNull());
    expect(queryExpanded()).toBe(false);
    expect(status!.isConnected).toBe(false);
  });

  it('automatically loads stored logs for the last seven days with a collapsed editor and compact counts', async (): Promise<void> => {
    const source = await ready(sessionSource());
    expect(document.querySelector('h1')).toBeNull();
    expect(document.querySelector('h2')?.textContent).toBe('Log analytics');
    expect(document.querySelector('.insight-heading p')).toBeNull();
    expect(queryExpanded()).toBe(false);
    expect(document.querySelector('.query-summary')?.textContent).toBe('Stored logs · Last 7 days');
    expect(source.reportQueries).toHaveLength(1);
    expect(source.reportQueries[0]).toMatchObject({ time_range: { start: '2026-10-24T12:00:00.000Z', end: '2026-10-31T12:00:00.000Z' }, filters: [], group_by: ['activity_kind', 'source', 'event_name', 'tool_name', 'session_id'] });
    expect(document.querySelectorAll('form')).toHaveLength(1);
    expect(document.querySelector('.stats')).toBeNull();
    expect(document.querySelector('.insight-result-meta')?.textContent).toContain('Log records on page3');
    expect(document.querySelector('.insight-result-meta')?.textContent).toContain('Rows on page1');
  });

  it('shows results without log details or auxiliary classification requests', async (): Promise<void> => {
    const source = await ready(sessionSource());
    expect(document.querySelectorAll('details')).toHaveLength(0);
    expect(document.querySelector('[aria-label="Scope log classifications"]')).toBeNull();
    expect(document.body.textContent).not.toContain('Log details');
    expect(document.body.textContent).not.toContain('not necessarily missed activity');
    expect(document.querySelector('table caption')).toBeNull();
    expect(document.querySelector('.section-heading')?.textContent).toBe('Stored logs');
    expect(document.body.textContent?.match(/Page 1/g)).toHaveLength(1);
    expect(source.queries).toHaveLength(1);
    await openQuery();
    await select('Report', 'Custom log query');
    button('Run query').click();
    await vi.waitFor((): void => expect(queryExpanded()).toBe(false));
    expect(document.querySelectorAll('details')).toHaveLength(0);
    expect(document.body.textContent).not.toContain('Log details');
    expect(source.queries).toHaveLength(2);
  });

  it('keeps the applied summary stable while editing and resetting without fetching', async (): Promise<void> => {
    const source = await ready();
    await openQuery();
    await select('Report', 'Tool calls');
    await select('Time range', 'Last 24 hours');
    expect(document.querySelector('.query-summary')?.textContent).toBe('Stored logs · Last 7 days');
    expect(source.reportQueries).toHaveLength(1);
    button('Run query').focus();
    button('Run query').click();
    await vi.waitFor(() => expect(queryExpanded()).toBe(false));
    expect(document.activeElement).toBe(queryTrigger());
    expect(document.querySelector('.query-summary')?.textContent).toBe('Tool calls · Last 24 hours');
    await openQuery();
    await select('Report', 'Custom log query');
    await select('Interval', 'Day');
    button('Reset').click();
    await tick();
    expect(queryExpanded()).toBe(true);
    expect(document.querySelector('.query-summary')?.textContent).toBe('Tool calls · Last 24 hours');
    expect(source.reportQueries).toHaveLength(2);
    expect(document.querySelector('.toolbar')?.textContent).toContain('Stored logs');
    expect(document.querySelector('.toolbar')?.textContent).toContain('Last 7 days');
    expect(document.querySelector('.section-heading h3')?.textContent).toBe('Tool calls');
  });

  it('leaves validation and failed queries open without replacing applied results', async (): Promise<void> => {
    const source = await ready();
    await openQuery();
    await select('Time range', 'Custom range');
    button('Run query').click();
    await vi.waitFor(() => expect(document.querySelector('[role="alert"]')?.textContent).toContain('both custom dates'));
    expect(queryExpanded()).toBe(true);
    expect(source.reportQueries).toHaveLength(1);
    input('analytics-start', '2026-10-31T09:00');
    input('analytics-end', '2026-10-31T10:00');
    input('analytics-offset', '-04:00');
    source.failure = new HttpError(503, 'Unavailable', {});
    button('Run query').click();
    await vi.waitFor(() => expect(document.querySelector('[role="alert"]')?.textContent).toContain('disabled'));
    expect(queryExpanded()).toBe(true);
    expect(document.querySelector('.query-summary')?.textContent).toBe('Stored logs · Last 7 days');
    source.failure = undefined;
    button('Retry query').click();
    await vi.waitFor(() => expect(document.querySelector('.query-summary')?.textContent).toBe('Stored logs · Custom range'));
    expect(source.reportQueries[2]).toEqual(source.reportQueries[1]);
    expect(source.reportQueries[2].time_range).toEqual({ start: '2026-10-31T13:00:00.000Z', end: '2026-10-31T14:00:00.000Z' });
  });

  it('preserves frozen pagination, session narrowing and retries despite edited drafts', async (): Promise<void> => {
    const source = await ready(sessionSource());
    const submitted = source.reportQueries[0];
    button('Next').click();
    await vi.waitFor(() => expect(document.querySelector('nav')?.textContent).toContain('Page 2'));
    await openQuery();
    await select('Report', 'Custom log query');
    await select('Time range', 'Last hour');
    source.failure = new Error('offline');
    button('View session  exact session ').click();
    await vi.waitFor(() => expect(document.querySelector('[role="alert"]')).not.toBeNull());
    expect(document.querySelector('.submitted-filters')).toBeNull();
    source.failure = undefined;
    source.response = { rows: [], has_more: false };
    button('Retry query').click();
    await vi.waitFor(() => expect(document.querySelector('.submitted-filters')?.textContent).toBe('Session ID:  exact session '));
    expect(source.reportQueries[3]).toEqual({ ...submitted, filters: [{ dimension: 'session_id', values: [' exact session '] }] });
    expect(document.querySelector('nav')?.textContent).toContain('Page 1');
    expect(document.querySelector('.query-summary')?.textContent).toBe('Stored logs · Last 7 days · Session ID:  exact session ');
    button('All sessions').click();
    await vi.waitFor(() => expect(document.querySelector('.submitted-filters')).toBeNull());
    expect(source.reportQueries[4]).toEqual(submitted);
    expect(document.querySelector('.toolbar')?.textContent).toContain('Custom log query');
  });

  it('keeps pending work visible, disables paging and fences a completion after unmount', async (): Promise<void> => {
    const source = await ready(sessionSource());
    let complete!: (response: LogCountResponse) => void;
    source.handler = () => new Promise((resolve) => { complete = resolve; });
    button('Next').click();
    await tick();
    expect(button('Next').disabled).toBe(true);
    expect(button('Previous').disabled).toBe(true);
    expect(button('View session  exact session ').disabled).toBe(true);
    expect(document.querySelector('[aria-label="Query results"]')?.getAttribute('aria-busy')).toBe('true');
    await unmount(component!);
    component = undefined;
    expect(source.signals.at(-1)?.aborted).toBe(true);
    complete({ rows: [], has_more: false });
    await tick();
    expect(document.querySelector('table')).toBeNull();
  });

  it('retains custom grouping, observed filters and empty values across report changes', async (): Promise<void> => {
    const source = await ready();
    await openQuery();
    await select('Report', 'Custom log query');
    await select('Interval', 'Day');
    await select('Time range', 'Last 24 hours');
    const sourceCheckbox = [...document.querySelectorAll<HTMLInputElement>('input[type="checkbox"]')].find((field) => field.parentElement?.textContent === 'Source');
    expect(sourceCheckbox).toBeDefined();
    sourceCheckbox!.click();
    source.response = { rows: [{ groups: [{ dimension: 'source', value: { kind: 'present', value: '' } }], count: 2, bucket: { kind: 'none' } }], has_more: false };
    button('+ Add filter').click();
    await vi.waitFor(() => expect(document.querySelector<HTMLInputElement>('input[role="combobox"]')?.disabled).toBe(false));
    const field = document.querySelector<HTMLInputElement>('input[role="combobox"]');
    expect(field).not.toBeNull();
    field!.focus();
    field!.click();
    await tick();
    const option = [...document.querySelectorAll<HTMLElement>('[role="option"]')].find((entry) => entry.textContent?.includes('Empty value'));
    expect(option).toBeDefined();
    option!.click();
    await tick();
    expect(document.querySelector('[aria-label="Selected filters"]')?.textContent).toContain('Empty value');
    await select('Report', 'File activity');
    await select('Report', 'Custom log query');
    source.response = { rows: [{ groups: [{ dimension: 'severity', value: { kind: 'missing' } }, { dimension: 'source', value: { kind: 'present', value: '' } }], count: 2, bucket: { kind: 'none' } }], has_more: false };
    button('Run query').click();
    await vi.waitFor(() => expect(queryExpanded()).toBe(false));
    expect(source.reportQueries.at(-1)).toMatchObject({ filters: [{ dimension: 'source', values: [''] }], group_by: ['severity', 'source'], bucketing: { kind: 'fixed', width: 'day' } });
    expect(document.querySelector('tbody')?.textContent).toContain('Missing attribute');
    expect(document.querySelector('tbody')?.textContent).toContain('Empty string');
    expect(document.querySelectorAll('tbody button')).toHaveLength(0);
  });

  it('keeps exact session entry inside the custom filter picker and validates its selection', async (): Promise<void> => {
    const source = await ready();
    expect(document.getElementById('analytics-session')).toBeNull();
    await openQuery();
    await select('Report', 'Custom log query');
    button('+ Add filter').click();
    await vi.waitFor(() => expect(document.querySelector<HTMLInputElement>('input[role="combobox"]')?.disabled).toBe(false));
    await select('Filter by', 'Session ID');
    expect(button('Add session filter').disabled).toBe(true);
    input('analytics-session', ' exact session ');
    await tick();
    button('Add session filter').click();
    await tick();
    expect(button('Add session filter').disabled).toBe(true);
    expect(document.querySelector('[aria-label="Selected filters"]')?.textContent).toContain('Session ID:  exact session ');
    button('Run query').click();
    await vi.waitFor(() => expect(queryExpanded()).toBe(false));
    expect(source.reportQueries.at(-1)?.filters).toEqual([{ dimension: 'session_id', values: [' exact session '] }]);
    await openQuery();
    await select('Report', 'Tool calls');
    expect(document.getElementById('analytics-session')).toBeNull();
    button('Run query').click();
    await vi.waitFor(() => expect(queryExpanded()).toBe(false));
    expect(source.reportQueries.at(-1)?.filters).toEqual([{ dimension: 'activity_kind', values: ['tool_call', 'file_read', 'file_edit'] }]);
  });

  it('recovers observed-value loading failures and chooses matching values with the keyboard', async (): Promise<void> => {
    const source = await ready();
    await openQuery();
    await select('Report', 'Custom log query');
    source.failure = new HttpError(422, 'Invalid query', {});
    button('+ Add filter').click();
    await vi.waitFor(() => expect(document.querySelector('[role="alert"]')?.textContent).toContain('query settings'));
    expect(source.reportQueries).toHaveLength(2);
    source.failure = undefined;
    source.response = { rows: [
      { groups: [{ dimension: 'source', value: { kind: 'present', value: 'worker' } }], count: 2, bucket: { kind: 'none' } },
      { groups: [{ dimension: 'source', value: { kind: 'present', value: 'api' } }], count: 3, bucket: { kind: 'none' } }
    ], has_more: false };
    button('Retry values').click();
    await vi.waitFor(() => expect(document.querySelector('[role="alert"]')).toBeNull());
    const field = document.querySelector<HTMLInputElement>('input[role="combobox"]');
    expect(field).not.toBeNull();
    field!.focus();
    field!.value = 'WORK';
    field!.dispatchEvent(new Event('input', { bubbles: true }));
    await tick();
    expect([...document.querySelectorAll('[role="option"]')].map((option) => option.textContent?.trim())).toEqual(['worker (2)']);
    field!.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
    await tick();
    expect(document.querySelector('[aria-label="Selected filters"]')?.textContent).toContain('worker');
    expect(document.querySelector('.section-heading h3')?.textContent).toBe('Stored logs');
    button('Run query').click();
    await vi.waitFor(() => expect(queryExpanded()).toBe(false));
    expect(source.reportQueries.at(-1)?.filters).toEqual([{ dimension: 'source', values: ['worker'] }]);
  });

  it('removes privileged content and notifies the owner when filter lookup access is revoked', async (): Promise<void> => {
    const source = sessionSource();
    let accessLosses = 0;
    render(source, () => { accessLosses++; });
    await vi.waitFor(() => expect(document.querySelector('table')).not.toBeNull());
    await openQuery();
    await select('Report', 'Custom log query');
    source.failure = new HttpError(403, 'Forbidden', {});
    button('+ Add filter').click();
    await vi.waitFor(() => expect(document.querySelector('form')).toBeNull());
    expect(document.querySelector('table')).toBeNull();
    expect(document.querySelector('[role="alert"]')?.textContent).toContain('Administration access');
    expect(accessLosses).toBe(1);
  });
});
