import type { beforeNavigate as registerBeforeNavigate } from '$app/navigation';
import { afterEach, expect, test, vi } from 'vitest';
import { flushSync, mount, tick, unmount } from 'svelte';
import { InMemoryAgentBehaviourApi } from '#lib/agent-behaviour/in-memory.test-support.js';
import { InMemoryLogCounts } from '#lib/admin/analytics/in-memory.test-support.js';
import { HttpError } from '#lib/admin/infrastructure/transport.js';
import InsightsHarness from './InsightsHarness.test-support.svelte';
import { InsightsHarnessState, configuration } from './insights.test-support.svelte';
import { InsightsState } from './insights-state.svelte';

type BeforeNavigate = Parameters<Parameters<typeof registerBeforeNavigate>[0]>[0];

const { beforeNavigate } = vi.hoisted(() => ({ beforeNavigate: vi.fn<typeof registerBeforeNavigate>() }));
vi.mock('$app/navigation', () => ({ beforeNavigate }));
vi.mock('$app/state', () => ({ navigating: { to: null, from: null }, page: { url: new URL('http://localhost/admin/insights/agent-behaviour') } }));
let component: ReturnType<typeof mount> | undefined;
afterEach(async (): Promise<void> => {
  if (component) await unmount(component);
  component = undefined;
  document.body.replaceChildren();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  beforeNavigate.mockClear();
});

function required<T extends Element>(selector: string): T {
  const found = document.querySelector<T>(selector);
  expect(found).not.toBeNull();
  return found!;
}

const diagnostics = '/admin/agent-diagnostics';
const reporting = '/admin/system-settings?section=agent-diagnostics';
const findings = '/admin/insights/agent-behaviour';
const logsPath = '/admin/insights/logs';
const findingsLink = `.subpage-container a[href="${findings}"]`;
const settingsLink = `.insight-heading a[href="${reporting}"]`;
const reportingLink = `.subpage-container a[href="${reporting}"]`;
const patternToggle = 'input[type="checkbox"][aria-label="Enable Missing context"]';
const logsTab = 'nav[aria-label="Insights views"] a[href="/admin/insights/logs"]';
const findingsTab = 'nav[aria-label="Insights views"] a[href="/admin/insights/agent-behaviour"]';
const activeAdminLink = 'nav[aria-label="Administration navigation"] a[aria-current="page"]';

function follow(selector: string): void {
  required<HTMLAnchorElement>(selector).click();
  flushSync();
}

test('preserves pattern drafts across standalone diagnostics, findings and log analytics', async (): Promise<void> => {
  const api = new InMemoryAgentBehaviourApi(); api.current = configuration();
  const logs = new InMemoryLogCounts();
  const list = vi.spyOn(api.reports, 'list');
  const get = vi.spyOn(api.configuration, 'get');
  const factory = vi.fn((): InsightsState => new InsightsState(api, logs));
  const controls = new InsightsHarnessState(diagnostics);
  component = mount(InsightsHarness, { target: document.body, props: { controls, createState: factory } });
  await vi.waitFor((): void => expect(document.querySelector(patternToggle)).not.toBeNull());
  expect(required('h1').textContent).toBe('Agent diagnostics');
  expect(required(activeAdminLink).getAttribute('href')).toBe(diagnostics);
  expect(document.querySelector('nav[aria-label="Insights views"]')).toBeNull();
  expect(document.querySelector('[aria-labelledby="reporting-settings-title"]')).toBeNull();
  expect(required('section[aria-labelledby="diagnostic-patterns-title"] header button').textContent).toBe('Add pattern');
  expect(required(reportingLink).textContent).toBe('Reporting settings');
  expect(required(findingsLink).textContent).toContain('View findings');
  required<HTMLInputElement>(patternToggle).click();
  flushSync();
  expect(document.body.textContent).toContain('Unsaved changes');

  follow(findingsLink);
  await vi.waitFor((): void => expect(list).toHaveBeenCalledTimes(1));
  expect(required('h1').textContent).toBe('Insights');
  expect(required(activeAdminLink).getAttribute('href')).toBe('/admin/insights/agent-behaviour');
  expect(required(findingsTab).getAttribute('aria-current')).toBe('page');
  expect(required('h2').textContent).toBe('Agent behaviour');
  expect(required<HTMLDetailsElement>('.query-panel').open).toBe(false);
  expect(required(settingsLink).textContent).toBe('Collection settings');
  expect(document.body.textContent).not.toContain('Add pattern');
  follow(logsTab);
  await vi.waitFor((): void => expect(logs.reportQueries).toHaveLength(1));
  expect(required('h2').textContent).toBe('Log analytics');
  expect(required<HTMLDetailsElement>('.query-panel').open).toBe(false);
  expect(required(logsTab).getAttribute('aria-current')).toBe('page');
  expect(document.querySelector(settingsLink)).toBeNull();
  follow(findingsTab);
  await vi.waitFor((): void => expect(list).toHaveBeenCalledTimes(2));
  follow(logsTab);
  await vi.waitFor((): void => expect(logs.reportQueries).toHaveLength(2));
  expect(required<HTMLDetailsElement>('.query-panel').open).toBe(false);
  expect(document.querySelector('.query-summary')?.textContent).toBe('Stored logs · Last 7 days');
  follow(`nav[aria-label="Administration navigation"] a[href="${diagnostics}"]`);
  expect(required<HTMLInputElement>(patternToggle).checked).toBe(false);
  expect(document.body.textContent).toContain('Unsaved changes');
  expect(factory).toHaveBeenCalledOnce();
  expect(get).toHaveBeenCalledOnce();
});

function navigation(path: string | null, type: 'link' | 'popstate' | 'leave'): BeforeNavigate {
  const target = (destination: string): NonNullable<BeforeNavigate['to']> => {
    const url = new URL(destination, 'http://localhost');
    const routeIds: Record<string, NonNullable<BeforeNavigate['to']>['route']['id']> = {
      [diagnostics]: '/admin/(agent-insights)/agent-diagnostics',
      [findings]: '/admin/(agent-insights)/insights/agent-behaviour',
      [`${findings}/configuration`]: '/admin/(agent-insights)/insights/agent-behaviour/configuration',
      [logsPath]: '/admin/(agent-insights)/insights/logs',
      '/admin/system-settings': '/admin/system-settings'
    };
    return { params: {}, route: { id: routeIds[url.pathname] ?? null }, url, scroll: null };
  };
  const details = { from: target(diagnostics), to: path ? target(path) : null, willUnload: !path, shallow: false, complete: Promise.resolve(), cancel: vi.fn() };
  if (type === 'link') return { ...details, type, event: new PointerEvent('click') };
  if (type === 'popstate') return { ...details, type, delta: -1, event: new PopStateEvent('popstate') };
  return { ...details, type };
}

test('guards unsaved pattern drafts only when leaving the shared Insights workspace', async (): Promise<void> => {
  const confirm = vi.fn<Window['confirm']>().mockReturnValue(false);
  vi.stubGlobal('confirm', confirm);
  const api = new InMemoryAgentBehaviourApi(); api.current = configuration();
  const controls = new InsightsHarnessState(diagnostics);
  component = mount(InsightsHarness, { target: document.body, props: { controls, createState: (): InsightsState => new InsightsState(api, new InMemoryLogCounts()) } });
  await vi.waitFor((): void => expect(document.querySelector(patternToggle)).not.toBeNull());

  const guard = beforeNavigate.mock.lastCall?.[0];
  if (!guard) throw new Error('Missing navigation guard');

  const cleanDeparture = navigation(reporting, 'link');
  guard(cleanDeparture);
  expect(cleanDeparture.cancel).not.toHaveBeenCalled();
  expect(confirm).not.toHaveBeenCalled();

  required<HTMLInputElement>(patternToggle).click();
  flushSync();
  for (const path of [findings, logsPath, diagnostics]) {
    const withinGroup = navigation(path, 'link');
    guard(withinGroup);
    expect(withinGroup.cancel).not.toHaveBeenCalled();
  }
  expect(confirm).not.toHaveBeenCalled();
  follow(findingsLink);

  const stay = navigation(reporting, 'link');
  guard(stay);
  expect(stay.cancel).toHaveBeenCalledOnce();
  expect(confirm).toHaveBeenCalledOnce();

  confirm.mockReturnValue(true);
  const departure = navigation(reporting, 'popstate');
  guard(departure);
  expect(departure.cancel).not.toHaveBeenCalled();
  expect(confirm).toHaveBeenCalledTimes(2);

  const unload = navigation(null, 'leave');
  guard(unload);
  expect(unload.cancel).toHaveBeenCalledOnce();
  expect(confirm).toHaveBeenCalledTimes(2);

  confirm.mockReturnValue(false);
  for (const path of [diagnostics, `${findings}/configuration`]) {
    const legacyReporting = navigation(`${path}?tab=reporting`, 'link');
    guard(legacyReporting);
    expect(legacyReporting.cancel).toHaveBeenCalledOnce();
  }
  expect(confirm).toHaveBeenCalledTimes(4);
});

test('guards an unfinished pattern category before it is added to the draft', async (): Promise<void> => {
  const confirm = vi.fn<Window['confirm']>().mockReturnValue(false);
  vi.stubGlobal('confirm', confirm);
  const api = new InMemoryAgentBehaviourApi(); api.current = configuration();
  const controls = new InsightsHarnessState(diagnostics);
  component = mount(InsightsHarness, { target: document.body, props: { controls, createState: (): InsightsState => new InsightsState(api, new InMemoryLogCounts()) } });
  const editButton = 'button[aria-label="Edit Missing context"]';
  await vi.waitFor((): void => expect(document.querySelector(editButton)).not.toBeNull());
  required<HTMLButtonElement>(editButton).click();
  flushSync();
  const category = required<HTMLInputElement>('#pattern-categories');
  category.value = 'unfinished-category';
  category.dispatchEvent(new Event('input', { bubbles: true }));
  expect(document.body.textContent).not.toContain('Unsaved changes');

  const guard = beforeNavigate.mock.lastCall?.[0];
  if (!guard) throw new Error('Missing navigation guard');
  const departure = navigation(reporting, 'link');
  guard(departure);
  expect(departure.cancel).toHaveBeenCalledOnce();
  expect(confirm).toHaveBeenCalledOnce();
});

test('identity changes and hidden identity destroy old pattern drafts rather than reusing them', async (): Promise<void> => {
  const controls = new InsightsHarnessState(diagnostics);
  const scopes: InsightsState[] = [];
  const factory = (): InsightsState => {
    const api = new InMemoryAgentBehaviourApi(); api.current = configuration();
    const state = new InsightsState(api, new InMemoryLogCounts()); scopes.push(state); return state;
  };
  component = mount(InsightsHarness, { target: document.body, props: { controls, createState: factory } }); flushSync();
  await vi.waitFor((): void => expect(document.querySelector(patternToggle)).not.toBeNull());
  required<HTMLInputElement>(patternToggle).click();
  flushSync();
  expect(document.body.textContent).toContain('Unsaved changes');
  controls.changeIdentity('account-b'); flushSync();
  await vi.waitFor((): void => expect(required<HTMLInputElement>(patternToggle).checked).toBe(true));
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
  component = mount(InsightsHarness, { target: document.body, props: { controls: new InsightsHarnessState(diagnostics), createState: (): InsightsState => state } });
  await vi.waitFor((): void => expect(document.querySelector(patternToggle)).not.toBeNull());
  required<HTMLInputElement>(patternToggle).click();
  flushSync();
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
  component = mount(InsightsHarness, { target: document.body, props: { controls: new InsightsHarnessState(), createState: (): InsightsState => state } });
  await vi.waitFor((): void => expect(document.querySelector('.collection-notice')?.textContent).toContain('Collection isn’t configured'));
  expect(required(`.collection-notice a[href="${diagnostics}"]`).textContent).toBe('Set up collection');
  expect(required('.query-panel summary').textContent).toContain('Query');
});

test('findings show collection is unconfigured when the last usable pattern is disabled and published', async (): Promise<void> => {
  const api = new InMemoryAgentBehaviourApi(); api.current = configuration();
  const state = new InsightsState(api, new InMemoryLogCounts());
  component = mount(InsightsHarness, { target: document.body, props: { controls: new InsightsHarnessState(diagnostics), createState: (): InsightsState => state } });
  await vi.waitFor((): void => expect(document.querySelector(patternToggle)).not.toBeNull());
  required<HTMLInputElement>(patternToggle).click();
  flushSync();
  follow(findingsLink);
  expect(document.querySelector('.collection-notice')).toBeNull();

  follow(`nav[aria-label="Administration navigation"] a[href="${diagnostics}"]`);
  const save = [...document.querySelectorAll<HTMLButtonElement>('.subpage-container button')].find((button): boolean => button.textContent === 'Save changes');
  if (!save) throw new Error('Missing Save changes button');
  expect(save.disabled).toBe(false);
  save.click();
  await vi.waitFor((): void => expect(document.body.textContent).toContain('Changes saved'));
  follow(findingsLink);
  expect(required('.collection-notice').textContent).toContain('Collection isn’t configured');
  expect(api.current.reporting_enabled).toBe(true);
  expect(required('.query-panel summary').textContent).toContain('Query');
});

test('findings show collection is off when saved reporting is off even with an excluded playbook', async (): Promise<void> => {
  const api = new InMemoryAgentBehaviourApi(); api.current = configuration();
  api.current.reporting_enabled = false;
  api.current.playbooks[0].enabled = false;
  const state = new InsightsState(api, new InMemoryLogCounts());
  component = mount(InsightsHarness, { target: document.body, props: { controls: new InsightsHarnessState(), createState: (): InsightsState => state } });
  await vi.waitFor((): void => expect(document.querySelector('.collection-notice')?.textContent).toContain('Collection is off'));
  expect(required('.collection-notice').textContent).toContain('Existing entries remain available.');
  expect(required(`.collection-notice a[href="${reporting}"]`).textContent).toBe('Review collection settings');
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
