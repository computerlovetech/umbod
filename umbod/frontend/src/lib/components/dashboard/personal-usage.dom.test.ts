import { afterEach, describe, expect, test, vi } from 'vitest';
import { flushSync, mount, tick, unmount } from 'svelte';
import { HttpError } from '$lib/admin/infrastructure/transport';
import type { UsagePort } from '$lib/dashboard/api';
import { personalUsageSchema, type PersonalUsage } from '$lib/dashboard/domain/usage-schemas';
import { InMemoryDashboardApi } from '$lib/dashboard/infrastructure/in-memory-api';
import { UsageState } from '$lib/dashboard/state/usage-state.svelte';
import { deferred, usageSnapshot } from '$lib/dashboard/usage-fixtures.test-support';
import { catalogue } from '$lib/dashboard/test-fixtures';
import * as personalConnectionsAdapter from '$lib/personal-connections/infrastructure/personal-connections-api';
import { InMemoryPersonalConnectionsApi } from '$lib/personal-connections/infrastructure/in-memory-api';
import { InMemoryWorkspaceApi } from '$lib/workspace/in-memory-api.test-support';
import type { WorkspaceProfile } from '$lib/workspace/domain/profile';
import PersonalUsageView from './PersonalUsage.svelte';
import Dashboard from './Dashboard.svelte';
import ConnectorsPage from './ConnectorsPage.svelte';

let component: ReturnType<typeof mount> | undefined;
let state: UsageState | undefined;

afterEach(async (): Promise<void> => {
  if (component) await unmount(component);
  state?.dispose();
  state = undefined;
  component = undefined;
  document.body.replaceChildren();
  vi.restoreAllMocks();
});

function button(label: string): HTMLButtonElement {
  const found = Array.from(document.querySelectorAll('button')).find((candidate) => candidate.textContent?.trim() === label);
  expect(found, label).toBeDefined();
  return found!;
}

function renderUsage(get: UsagePort['get']): UsageState {
  const usage = new UsageState({ get }, (): void => {});
  state = usage;
  component = mount(PersonalUsageView, { target: document.body, props: { state: usage, signIn: (): void => {} } });
  flushSync();
  return usage;
}

describe('personal usage presentation', () => {
  test('pending, unavailable and retry are distinct from successful empty usage', async (): Promise<void> => {
    const pending = deferred<PersonalUsage>();
    const get = vi.fn<UsagePort['get']>().mockReturnValueOnce(pending.promise).mockResolvedValue(usageSnapshot());
    renderUsage(get);
    button('Refresh usage').click();
    await tick();
    expect(document.querySelector('.usage')?.getAttribute('aria-busy')).toBe('true');
    expect(button('Refresh usage').disabled).toBe(true);
    expect(document.querySelector('.empty-ranking')).toBeNull();
    expect(document.querySelector('[aria-label="Tool activity"]')).toBeNull();
    pending.reject(new HttpError(503, 'private diagnostic', { secret: 'secret' }));
    await vi.waitFor(() => expect(document.querySelector('[role="alert"]')?.textContent).toBe('Usage unavailable'));
    expect(document.body.textContent).not.toContain('No usage yet');
    expect(document.body.textContent).not.toContain('private diagnostic');
    expect(document.querySelector('.empty-ranking')).toBeNull();
    button('Retry usage').click();
    await vi.waitFor(() => expect(document.querySelector('[aria-label="Tool activity"]')).not.toBeNull());
    expect(document.querySelector('[role="group"][aria-label^="Daily tool calls"]')?.getAttribute('aria-label')).toContain('7 days. 0 tool calls');
    expect(document.querySelectorAll('.dv-bar[role="img"]')).toHaveLength(0);
    expect(document.querySelector('.dv-plot')).not.toBeNull();
    expect(document.querySelector('.dv-ring')).not.toBeNull();
    expect(document.querySelector('.dv-mix-bar')).not.toBeNull();
    expect(document.querySelectorAll('.dashboard-panel')).toHaveLength(4);
    expect(document.querySelectorAll('.empty-ranking-row')).toHaveLength(5);
    expect(document.querySelector('[role="img"][aria-label="No per-tool usage data"]')).not.toBeNull();
    expect(document.querySelectorAll('.tool-ranking li')).toHaveLength(0);
    expect(document.querySelectorAll('.dv-outcome-legend dd, .dv-mix-legend dd').length).toBeGreaterThan(0);
    expect(Array.from(document.querySelectorAll('.dv-outcome-legend dd, .dv-mix-legend dd')).every((value) => value.textContent === '')).toBe(true);
    expect(document.querySelector('[aria-label="Tool activity"]')?.textContent).not.toContain('0 calls');
    expect(document.body.textContent).not.toMatch(/No usage yet|No tool calls|No operations|Per-tool usage|Unavailable/);
    expect(document.querySelector('[role="status"]')).toBeNull();
    expect(document.querySelector('[aria-label="No tool calls"]')).not.toBeNull();
    expect(document.querySelector('.updated time')?.getAttribute('datetime')).toBe('2026-11-09T12:00:00.000Z');
  });

  test('resources-only usage does not imply tool activity or fabricate a ranking', async (): Promise<void> => {
    const snapshot = usageSnapshot();
    const counts = { ...snapshot.totals, resource: { success: 5, failure: 2, cancelled: 3 } };
    const result = personalUsageSchema.parse({
      ...snapshot, totals: counts,
      daily: snapshot.daily.map((row, index) => index === 0 ? { ...row, counts } : row)
    });
    renderUsage(vi.fn<UsagePort['get']>().mockResolvedValue(result));
    button('Refresh usage').click();
    await vi.waitFor(() => expect(document.querySelector('[aria-label="Tool activity"]')).not.toBeNull());
    expect(document.querySelector('[aria-label="No tool calls"]')).not.toBeNull();
    expect(document.querySelector('[aria-label="Operation mix"]')?.textContent).toContain('100.0%');
    expect(document.querySelector('[aria-label="Tool activity"]')?.textContent).not.toContain('0 calls');
    expect(document.querySelector('[aria-label="Most-used tools"] h3')?.textContent).toBe('Most-used tools');
    expect(document.querySelectorAll('.empty-ranking-row')).toHaveLength(5);
    expect(document.querySelectorAll('input[type="checkbox"]')).toHaveLength(0);
    expect(document.querySelector('[aria-label="No per-tool usage data"]')).not.toBeNull();
    expect(document.querySelectorAll('.tool-ranking li')).toHaveLength(0);
    expect(document.body.textContent).not.toContain('No usage yet');
  });

  test('failure retry and controlled period selection fence late responses', async (): Promise<void> => {
    const pending = deferred<PersonalUsage>();
    const get = vi.fn<UsagePort['get']>()
      .mockRejectedValueOnce(new Error('private'))
      .mockReturnValueOnce(pending.promise)
      .mockResolvedValue(usageSnapshot(30, 'account-one', 1));
    renderUsage(get);
    button('Refresh usage').click();
    await vi.waitFor(() => expect(document.querySelector('[role="alert"]')?.textContent).toBe("Couldn't load usage"));
    button('Retry usage').click();
    await tick();
    expect(button('7 days').getAttribute('aria-pressed')).toBe('true');
    expect(document.querySelector('[role="combobox"]')).toBeNull();
    button('30 days').click();
    await vi.waitFor(() => expect(document.querySelectorAll('.dv-bar[role="img"]')).toHaveLength(30));
    expect(button('30 days').getAttribute('aria-pressed')).toBe('true');
    expect(button('7 days').getAttribute('aria-pressed')).toBe('false');
    expect(get.mock.calls.map(([days]) => days)).toEqual([7, 7, 30]);
    pending.resolve(usageSnapshot());
    await tick();
    expect(document.querySelectorAll('.dv-bar[role="img"]')).toHaveLength(30);
    expect(document.querySelector('[aria-label="Tool activity"]')?.textContent).toContain('30 calls');
  });

  test('identity changes remove old account counts before replacement', async (): Promise<void> => {
    const pending = deferred<PersonalUsage>();
    const get = vi.fn<UsagePort['get']>().mockResolvedValueOnce(usageSnapshot(7, 'account-one', 9)).mockReturnValueOnce(pending.promise);
    const usage = renderUsage(get);
    button('Refresh usage').click();
    await vi.waitFor(() => expect(document.querySelector('[aria-label="Tool activity"]')).not.toBeNull());
    usage.reconcileIdentity('account-two');
    await tick();
    expect(document.querySelector('[aria-label="Tool activity"]')).toBeNull();
    pending.resolve(usageSnapshot(7, 'account-two', 1));
    await vi.waitFor(() => expect(document.querySelector('[aria-label="Tool activity"]')?.textContent).toContain('7 calls'));
  });

  test.each(['pending', 'loaded'] as const)('profile identity B fences %s account A data while the header switches', async (initialPhase): Promise<void> => {
    const profileB = deferred<WorkspaceProfile>();
    const usageA = deferred<PersonalUsage>();
    const usageB = deferred<PersonalUsage>();
    const api = new InMemoryDashboardApi({ ...catalogue, personal_enabled: false });
    const list = vi.spyOn(api.catalogue, 'list');
    const get = vi.spyOn(api.usage, 'get').mockReturnValueOnce(usageA.promise).mockReturnValue(usageB.promise);
    component = mount(Dashboard, { target: document.body, props: {
      accountIdentity: { kind: 'visible', name: 'Account A', email: null, picture: null, hiddenValues: { id: 'header-account-a' } },
      createApi: () => api,
      createWorkspaceApi: () => ({ profile: { get: (): Promise<WorkspaceProfile> => profileB.promise } })
    } });
    await vi.waitFor(() => expect(get).toHaveBeenCalledTimes(1));
    const usageSignalA = get.mock.calls[0][1];
    if (initialPhase === 'loaded') {
      usageA.resolve(usageSnapshot(7, 'account-one', 9));
      await vi.waitFor(() => expect(document.querySelector('[aria-label="Tool activity"]')?.textContent).toContain('63 calls'));
    }
    profileB.resolve({
      user: { id: 'header-account-b', name: 'Account B', email: null, picture: null },
      capabilities: { administration: false }
    });
    await vi.waitFor(() => expect(document.querySelector('[aria-label="Workspace sidebar"]')?.textContent).toContain('Account B'));
    expect(usageSignalA?.aborted).toBe(true);
    expect(document.querySelector('[aria-label="Tool activity"]')).toBeNull();
    expect(list).not.toHaveBeenCalled();
    expect(get).toHaveBeenCalledTimes(2);
    usageA.resolve(usageSnapshot(7, 'account-one', 9));
    await tick();
    expect(document.querySelector('[aria-label="Tool activity"]')).toBeNull();
    usageB.resolve(usageSnapshot(7, 'account-two', 1));
    await vi.waitFor(() => expect(document.querySelector('[aria-label="Tool activity"]')?.textContent).toContain('7 calls'));
    expect(document.querySelector('[aria-label="Workspace sidebar"]')?.textContent).toContain('Account B');
  });

  test('Connectors loads its catalogue without requesting usage while the profile is pending', async (): Promise<void> => {
    const api = new InMemoryDashboardApi({ ...catalogue, personal_enabled: false });
    const get = vi.spyOn(api.usage, 'get');
    component = mount(ConnectorsPage, { target: document.body, props: {
      createApi: () => api,
      createPersonalApi: () => new InMemoryPersonalConnectionsApi([]),
      createWorkspaceApi: () => ({ profile: { get: () => new Promise<WorkspaceProfile>((): void => {}) } })
    } });
    await vi.waitFor(() => expect(document.querySelector('[aria-labelledby="connectors-heading"]')?.getAttribute('aria-busy')).toBe('false'));
    expect(document.querySelector('[aria-labelledby="connectors-heading"]')?.textContent).toContain('Shared calendar');
    expect(document.querySelector('[aria-current="page"]')?.getAttribute('href')).toBe('/connectors');
    expect(document.querySelector('.usage')).toBeNull();
    window.dispatchEvent(new Event('focus'));
    await tick();
    expect(get).not.toHaveBeenCalled();
  });

  test('Dashboard loads and refreshes usage without catalogue or personal requests; unmount aborts', async (): Promise<void> => {
    const catalogueRead = deferred<typeof catalogue>();
    const pending = deferred<PersonalUsage>();
    const api = new InMemoryDashboardApi({ ...catalogue, personal_enabled: false });
    const list = vi.spyOn(api.catalogue, 'list').mockReturnValue(catalogueRead.promise);
    const personal = new InMemoryPersonalConnectionsApi([]);
    const personalList = vi.spyOn(personal.connections, 'list');
    const createPersonalApi = vi.spyOn(personalConnectionsAdapter, 'browserPersonalConnectionsApi').mockReturnValue(personal);
    const get = vi.spyOn(api.usage, 'get').mockResolvedValueOnce(usageSnapshot(7, 'account-one', 1)).mockReturnValueOnce(pending.promise);
    const workspace = new InMemoryWorkspaceApi({ user: { id: 'member', name: 'Member', email: null, picture: null }, capabilities: { administration: false } });
    vi.spyOn(workspace.profile, 'get').mockReturnValue(new Promise((): void => {}));
    component = mount(Dashboard, { target: document.body, props: {
      createApi: () => api,
      createWorkspaceApi: () => workspace
    } });
    await vi.waitFor(() => expect(document.querySelector('[aria-label="Tool activity"]')).not.toBeNull());
    expect(document.querySelector('[aria-labelledby="connectors-heading"]')).toBeNull();
    expect(list).not.toHaveBeenCalled();
    expect(personalList).not.toHaveBeenCalled();
    expect(createPersonalApi).not.toHaveBeenCalled();
    expect(document.querySelector('.usage')?.getAttribute('aria-busy')).toBe('false');
    expect(document.querySelector('a[href="/admin"]')).toBeNull();
    button('Refresh usage').click();
    await tick();
    expect(get).toHaveBeenCalledTimes(2);
    const signal = get.mock.calls[1][1];
    await unmount(component!);
    component = undefined;
    expect(signal?.aborted).toBe(true);
    pending.resolve(usageSnapshot());
    catalogueRead.resolve(catalogue);
    await tick();
    expect(document.querySelector('[aria-label="Tool activity"]')).toBeNull();
  });
});
