import { afterEach, expect, test, vi } from 'vitest';
import { flushSync, mount, tick, unmount } from 'svelte';
import { InMemoryAgentBehaviourApi } from '#lib/agent-behaviour/in-memory.test-support.js';
import { InMemoryLogCounts } from '#lib/admin/analytics/in-memory.test-support.js';
import { HttpError } from '#lib/admin/infrastructure/transport.js';
import InsightsHarness from './InsightsHarness.test-support.svelte';
import { InsightsHarnessState, configuration } from './insights.test-support.svelte';
import { InsightsState } from './insights-state.svelte';

vi.mock('$app/state', () => ({ navigating: { to: null, from: null }, page: { url: new URL('http://localhost/admin/agent-diagnostics') } }));
let component: ReturnType<typeof mount> | undefined;
afterEach(async (): Promise<void> => {
  if (component) await unmount(component);
  component = undefined;
  document.body.replaceChildren();
  vi.restoreAllMocks();
});

function required<T extends Element>(selector: string): T {
  const found = document.querySelector<T>(selector);
  expect(found).not.toBeNull();
  return found!;
}

const findingsLink = '.subpage-container a[href="/admin/insights/agent-behaviour"]';
const settingsLink = '.insight-heading a[href="/admin/agent-diagnostics"]';
const logsTab = 'nav[aria-label="Insights views"] a[href="/admin/insights/logs"]';
const findingsTab = 'nav[aria-label="Insights views"] a[href="/admin/insights/agent-behaviour"]';
const activeAdminLink = 'nav[aria-label="Administration navigation"] a[aria-current="page"]';

function follow(selector: string): void {
  required<HTMLAnchorElement>(selector).click();
  flushSync();
}

test('preserves configuration drafts across separate findings and analytics routes with contextual header actions', async (): Promise<void> => {
  const api = new InMemoryAgentBehaviourApi(); api.current = configuration();
  const logs = new InMemoryLogCounts();
  const list = vi.spyOn(api.reports, 'list');
  const get = vi.spyOn(api.configuration, 'get');
  const factory = vi.fn((): InsightsState => new InsightsState(api, logs));
  component = mount(InsightsHarness, { target: document.body, props: { controls: new InsightsHarnessState(), createState: factory } }); flushSync();
  await vi.waitFor((): void => expect(document.querySelector('label[aria-label="Enable Missing context"] input')).not.toBeNull());
  expect(required('h1').textContent).toBe('Agent diagnostics');
  expect(required(activeAdminLink).getAttribute('href')).toBe('/admin/agent-diagnostics');
  expect(document.querySelector('nav[aria-label="Insights views"]')).toBeNull();
  const diagnosticsTabs = required('nav[aria-label="Agent diagnostics subpages"]');
  expect(diagnosticsTabs.querySelector('[aria-current="page"]')?.textContent).toBe('Patterns');
  expect(diagnosticsTabs.querySelector('a[href$="?tab=reporting"]')?.textContent).toBe('Reporting settings');
  expect(required('section[aria-labelledby="diagnostic-patterns-title"] header button').textContent).toBe('Add pattern');
  expect(required(findingsLink).textContent).toContain('View findings');
  required<HTMLInputElement>('label[aria-label="Enable Missing context"] input').click(); flushSync();
  expect(document.body.textContent).toContain('Unsaved changes');
  follow(findingsLink);
  await vi.waitFor((): void => expect(list).toHaveBeenCalledTimes(1));
  expect(required('h1').textContent).toBe('Insights');
  expect(required(activeAdminLink).getAttribute('href')).toBe('/admin/insights/agent-behaviour');
  expect(required(findingsTab).getAttribute('aria-current')).toBe('page');
  expect(required('h2').textContent).toBe('Agent behaviour');
  expect(required<HTMLDetailsElement>('.query-panel').open).toBe(false);
  expect(document.querySelector('[role="tablist"]')).toBeNull();
  expect(required(settingsLink).textContent).toBe('Collection settings');
  expect(document.querySelectorAll('.subpage-container a[href="/admin/agent-diagnostics"]')).toHaveLength(1);
  expect(document.body.textContent).not.toContain('Add pattern');
  follow(logsTab);
  await vi.waitFor((): void => expect(logs.reportQueries).toHaveLength(1));
  expect(required('h2').textContent).toBe('Log analytics');
  expect(required<HTMLDetailsElement>('.query-panel').open).toBe(false);
  expect(required(logsTab).getAttribute('aria-current')).toBe('page');
  expect(document.querySelector('.subpage-container a[href="/admin/agent-diagnostics"]')).toBeNull();
  follow(findingsTab);
  await vi.waitFor((): void => expect(list).toHaveBeenCalledTimes(2));
  follow(logsTab);
  await vi.waitFor((): void => expect(logs.reportQueries).toHaveLength(2));
  expect(required<HTMLDetailsElement>('.query-panel').open).toBe(false);
  expect(document.querySelector('.query-summary')?.textContent).toBe('Stored logs · Last 7 days');
  follow(findingsTab);
  await vi.waitFor((): void => expect(list).toHaveBeenCalledTimes(3));
  follow(settingsLink);
  expect(required<HTMLInputElement>('label[aria-label="Enable Missing context"] input').checked).toBe(false);
  expect(document.body.textContent).toContain('Unsaved changes');
  expect(factory).toHaveBeenCalledOnce();
  expect(get).toHaveBeenCalledOnce();
});

test('identity changes and hidden identity destroy old drafts rather than reusing them', async (): Promise<void> => {
  const controls = new InsightsHarnessState();
  const scopes: InsightsState[] = [];
  const factory = (): InsightsState => {
    const api = new InMemoryAgentBehaviourApi(); api.current = configuration();
    const state = new InsightsState(api, new InMemoryLogCounts()); scopes.push(state); return state;
  };
  component = mount(InsightsHarness, { target: document.body, props: { controls, createState: factory } }); flushSync();
  await vi.waitFor((): void => expect(document.querySelector('label[aria-label="Enable Missing context"] input')).not.toBeNull());
  required<HTMLInputElement>('label[aria-label="Enable Missing context"] input').click(); flushSync();
  expect(document.body.textContent).toContain('Unsaved changes');
  controls.changeIdentity('account-b'); flushSync();
  await vi.waitFor((): void => expect(document.querySelector('label[aria-label="Enable Missing context"] input')).not.toBeNull());
  expect(required<HTMLInputElement>('label[aria-label="Enable Missing context"] input').checked).toBe(true);
  expect(scopes).toHaveLength(2);
  expect(scopes[0].allowed).toBe(false);
  expect(scopes[0].behaviour.configuration.patterns).toEqual([]);
  controls.hideIdentity(); flushSync(); await tick();
  expect(scopes[1].allowed).toBe(false);
  expect(document.querySelector('form')).toBeNull();
  expect(document.querySelector('[role="alert"]')?.textContent).toContain('Administration access');
});

test('a log-query authorization failure clears cached configuration and removes every Insights action', async (): Promise<void> => {
  const api = new InMemoryAgentBehaviourApi(); api.current = configuration();
  const logs = new InMemoryLogCounts();
  const state = new InsightsState(api, logs);
  component = mount(InsightsHarness, { target: document.body, props: { controls: new InsightsHarnessState(), createState: (): InsightsState => state } }); flushSync();
  await vi.waitFor((): void => expect(document.querySelector('label[aria-label="Enable Missing context"] input')).not.toBeNull());
  required<HTMLInputElement>('label[aria-label="Enable Missing context"] input').click(); flushSync();
  logs.failure = new HttpError(403, 'Forbidden', null);
  follow(findingsLink);
  follow(logsTab);
  await vi.waitFor((): void => expect(document.querySelector('[role="alert"]')?.textContent).toContain('Administration access'));
  expect(state.behaviour.configuration.patterns).toEqual([]);
  expect(document.querySelector('nav[aria-label="Insights views"]')).toBeNull();
  expect(document.querySelector('.query-panel')).toBeNull();
  expect(document.querySelector(settingsLink)).toBeNull();
  expect(document.querySelector(findingsLink)).toBeNull();
});

test('findings offer setup when collection is unpublished and still show the query', async (): Promise<void> => {
  const state = new InsightsState(new InMemoryAgentBehaviourApi(), new InMemoryLogCounts());
  const controls = new InsightsHarnessState('/admin/insights/agent-behaviour');
  component = mount(InsightsHarness, { target: document.body, props: { controls, createState: (): InsightsState => state } });
  await vi.waitFor((): void => expect(document.querySelector('.collection-notice')?.textContent).toContain('Collection isn’t configured'));
  expect(required('.collection-notice a[href="/admin/agent-diagnostics"]').textContent).toBe('Set up collection');
  expect(required('.query-panel summary').textContent).toContain('Query');
});

test('findings show collection is off only after the disabling draft is published', async (): Promise<void> => {
  const api = new InMemoryAgentBehaviourApi(); api.current = configuration();
  const state = new InsightsState(api, new InMemoryLogCounts());
  component = mount(InsightsHarness, { target: document.body, props: { controls: new InsightsHarnessState(), createState: (): InsightsState => state } });
  await vi.waitFor((): void => expect(document.querySelector('label[aria-label="Enable Missing context"] input')).not.toBeNull());
  required<HTMLInputElement>('label[aria-label="Enable Missing context"] input').click(); flushSync();
  expect(document.body.textContent).toContain('Unsaved changes');
  follow(findingsLink);
  expect(document.querySelector('.collection-notice')).toBeNull();

  follow(settingsLink);
  const save = Array.from(document.querySelectorAll<HTMLButtonElement>('.subpage-container button')).find((button): boolean => button.textContent === 'Save changes');
  expect(save).toBeDefined();
  expect(save!.disabled).toBe(false);
  save!.click();
  await vi.waitFor((): void => expect(document.body.textContent).toContain('Changes saved'));
  follow(findingsLink);
  expect(required('.collection-notice').textContent).toContain('Collection is off');
  expect(required('.collection-notice').textContent).toContain('Existing entries remain available.');
  expect(required('.collection-notice a[href="/admin/agent-diagnostics"]').textContent).toBe('Review collection settings');
  expect(required('.query-panel summary').textContent).toContain('Query');
});

test('a failed findings query shows the error instead of a false empty result', async (): Promise<void> => {
  const api = new InMemoryAgentBehaviourApi(); api.current = configuration();
  vi.spyOn(api.reports, 'list').mockRejectedValueOnce(new HttpError(503, 'Unavailable', null));
  const state = new InsightsState(api, new InMemoryLogCounts());
  const controls = new InsightsHarnessState('/admin/insights/agent-behaviour');
  component = mount(InsightsHarness, { target: document.body, props: { controls, createState: (): InsightsState => state } });
  await vi.waitFor((): void => expect(document.body.textContent).toContain('Entries could not be loaded'));
  expect(document.querySelector('section[aria-label="Entries"]')).toBeNull();
  const query = required<HTMLDetailsElement>('.query-panel');
  query.open = true;
  required<HTMLButtonElement>('#agent-behaviour-query button[type="submit"]').click();
  await vi.waitFor((): void => expect(document.body.textContent).toContain('No entries match this query.'));
  expect(query.open).toBe(false);
  expect(document.body.textContent).not.toContain('Entries could not be loaded');
});
