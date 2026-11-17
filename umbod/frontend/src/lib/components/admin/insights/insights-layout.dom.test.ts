import { afterEach, expect, test, vi } from 'vitest';
import { flushSync, mount, tick, unmount } from 'svelte';
import { InMemoryAgentBehaviourApi } from '#lib/agent-behaviour/in-memory.test-support.js';
import { InMemoryLogCounts } from '#lib/admin/analytics/in-memory.test-support.js';
import { HttpError } from '#lib/admin/infrastructure/transport.js';
import InsightsHarness from './InsightsHarness.test-support.svelte';
import { InsightsHarnessState, configuration } from './insights.test-support.svelte';
import { InsightsState } from './insights-state.svelte';

vi.mock('$app/state', () => ({ navigating: { to: null, from: null } }));
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

function navigate(section: 'behaviour' | 'logs'): void {
  required<HTMLAnchorElement>(`nav[aria-label="Insights views"] a[href="/admin/insights/${section === 'behaviour' ? 'agent-behaviour' : 'logs'}"]`).click();
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
  expect(required('h1').textContent).toBe('Insights');
  expect(required('nav[aria-label="Insights views"] a[aria-current="location"]').textContent).toBe('Agent behaviour');
  expect(document.querySelector('a[href$="/configuration"]')).toBeNull();
  expect(document.body.textContent).toContain('Add pattern');
  required<HTMLInputElement>('label[aria-label="Enable Missing context"] input').click(); flushSync();
  expect(document.body.textContent).toContain('Unsaved changes');
  navigate('behaviour');
  await vi.waitFor((): void => expect(list).toHaveBeenCalledTimes(1));
  expect(required('h2').textContent).toBe('Agent behaviour');
  expect(required<HTMLDetailsElement>('.query-panel').open).toBe(false);
  expect(document.querySelector('[role="tablist"]')).toBeNull();
  expect(required('header a[href$="/configuration"]').textContent).toBe('Configure');
  expect(document.body.textContent).not.toContain('Add pattern');
  navigate('logs');
  await vi.waitFor((): void => expect(logs.reportQueries).toHaveLength(1));
  expect(required('h2').textContent).toBe('Log analytics');
  expect(required<HTMLDetailsElement>('.query-panel').open).toBe(false);
  expect(document.querySelector('a[href$="/configuration"]')).toBeNull();
  navigate('behaviour');
  await vi.waitFor((): void => expect(list).toHaveBeenCalledTimes(2));
  navigate('logs');
  await vi.waitFor((): void => expect(logs.reportQueries).toHaveLength(2));
  expect(required<HTMLDetailsElement>('.query-panel').open).toBe(false);
  expect(document.querySelector('.query-summary')?.textContent).toBe('Stored logs · Last 7 days');
  navigate('behaviour');
  await vi.waitFor((): void => expect(list).toHaveBeenCalledTimes(3));
  required<HTMLAnchorElement>('header a[href$="/configuration"]').click(); flushSync();
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
  navigate('logs');
  await vi.waitFor((): void => expect(document.querySelector('[role="alert"]')?.textContent).toContain('Administration access'));
  expect(state.behaviour.configuration.patterns).toEqual([]);
  expect(document.querySelector('nav[aria-label="Insights views"]')).toBeNull();
  expect(document.querySelector('.query-panel')).toBeNull();
  expect(document.querySelector('header a[href$="/configuration"]')).toBeNull();
});
