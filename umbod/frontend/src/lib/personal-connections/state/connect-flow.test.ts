import { describe, expect, test, vi } from 'vitest';
import { HttpError, NetworkError } from '$lib/admin/infrastructure/transport';
import { InMemoryDashboardApi } from '$lib/dashboard/infrastructure/in-memory-api';
import { DashboardState } from '$lib/dashboard/state/dashboard-state.svelte';
import { catalogue } from '$lib/dashboard/test-fixtures';
import type { PersonalConnectionsApi } from '../api';
import type { AttemptScheduler } from '../attempt-scheduler';
import { InMemoryAttemptScheduler } from '../infrastructure/in-memory-attempt-scheduler';
import { InMemoryAuthorizationBrowser } from '../infrastructure/in-memory-authorization-browser';
import { InMemoryPersonalConnectionsApi } from '../infrastructure/in-memory-api';
import { authorizationHealth, completedAttempt, deferred, pendingAttempt, selection } from '../test-fixtures';
import type { Attempt, Selection } from '../domain/schemas';
import { PersonalAccessViewState } from './access-view-state.svelte';
import { ConnectionState } from './connection-state.svelte';
import type { PersonalConnectionController } from './port';

function harness(saved = false): { state: PersonalConnectionController; api: PersonalConnectionsApi; clock: InMemoryAttemptScheduler; browser: InMemoryAuthorizationBrowser; changed: () => Promise<void> } {
  const initial: Selection = { ...selection, enabled: false, has_authorization: saved };
  const api: PersonalConnectionsApi = new InMemoryPersonalConnectionsApi([initial], { calendar: saved ? authorizationHealth : { state: 'not_authorized' } });
  const clock = new InMemoryAttemptScheduler();
  const scheduler: AttemptScheduler = clock;
  const browser = new InMemoryAuthorizationBrowser();
  const changed = vi.fn<() => Promise<void>>().mockResolvedValue();
  const state: PersonalConnectionController = new ConnectionState(initial, api, (): void => {}, changed, browser, scheduler);
  return { state, api, clock, browser, changed };
}

async function authorize(api: PersonalConnectionsApi): Promise<void> {
  vi.spyOn(api.authorization, 'getHealth').mockResolvedValue(authorizationHealth);
  vi.spyOn(api.connections, 'get').mockResolvedValue(selection);
  vi.spyOn(api.authorization, 'get').mockResolvedValue(completedAttempt);
}

describe('single click personal connection through public ports', () => {
  test('controller Connect reserves before enabling and initiates exactly once', async (): Promise<void> => {
    const { state, api, clock, browser } = harness();
    const enabling = deferred<Selection>();
    const enable = vi.spyOn(api.connections, 'setEnablement').mockImplementation(() => {
      expect(browser.windows).toHaveLength(1);
      return enabling.promise;
    });
    vi.spyOn(api.connections, 'get').mockResolvedValue({ ...selection, has_authorization: false });
    const start = vi.spyOn(api.authorization, 'start').mockResolvedValue(pendingAttempt);
    const view = new PersonalAccessViewState(() => state);
    const connecting = state.connect();
    await state.connect();
    expect(enable).toHaveBeenCalledOnce();
    enabling.resolve({ ...selection, has_authorization: false });
    await connecting;
    expect(start).toHaveBeenCalledOnce();
    expect(browser.windows[0].url).toBe(pendingAttempt.authorization_url);
    expect(state.authorizationOpened).toBe(true);
    expect(state.monitoring).toBe(true);
    expect(view.status.action).toBeNull();
    expect(view.menuActions.some((action) => action.id === 'check')).toBe(true);
    expect(clock.pending).toBe(1);
    state.dispose();
    expect(clock.pending).toBe(0);
  });

  test('reenabling usable authorization loads missing tools without consent', async (): Promise<void> => {
    const { state, api, browser, clock } = harness(true);
    const start = vi.spyOn(api.authorization, 'start');
    const discover = vi.spyOn(api.connections, 'discover');
    await state.connect();
    expect(start).not.toHaveBeenCalled();
    expect(discover).toHaveBeenCalledOnce();
    expect(state.selection.runtime_available).toBe(false);
    expect(browser.windows[0].closed).toBe(true);
    expect(clock.pending).toBe(0);
    state.dispose();
  });

  test('automatic completion reads authorized owner facts before one discovery and catalogue refresh', async (): Promise<void> => {
    const { state, api, clock, changed } = harness();
    await state.connect();
    await authorize(api);
    const discovering = deferred<void>();
    const discover = vi.spyOn(api.connections, 'discover').mockReturnValue(discovering.promise);
    const checking = clock.advance();
    await vi.waitFor(() => expect(discover).toHaveBeenCalledOnce());
    expect(state.loadingTools).toBe(true);
    expect(new PersonalAccessViewState(() => state).status.label).toBe('Loading tools');
    await state.connect();
    await state.discover();
    discovering.resolve();
    await checking;
    expect(discover).toHaveBeenCalledOnce();
    expect(changed).toHaveBeenCalledOnce();
    expect(state.attempt).toBeNull();
    expect(clock.pending).toBe(0);
    state.dispose();
  });

  test.each(['cancel', 'disable', 'disconnect', 'dispose'] as const)('%s stops monitoring and rejects a late completed read', async (action): Promise<void> => {
    const { state, api, clock } = harness();
    await state.connect();
    const result = deferred<Attempt>();
    vi.spyOn(api.authorization, 'get').mockReturnValue(result.promise);
    const discover = vi.spyOn(api.connections, 'discover');
    const checking = clock.advance();
    expect(state.busy).toBe(false);
    if (action === 'cancel') await state.cancel();
    if (action === 'disable') await state.setEnabled();
    if (action === 'disconnect') { state.requestDisconnect(); await state.disconnect(); }
    if (action === 'dispose') state.dispose();
    result.resolve(completedAttempt);
    await checking;
    expect(discover).not.toHaveBeenCalled();
    expect(clock.pending).toBe(0);
    state.dispose();
  });

  test('transient read failures back off, do not block cleanup, and pause after ten minutes', async (): Promise<void> => {
    const { state, api, clock } = harness();
    const start = vi.spyOn(api.authorization, 'start');
    await state.connect();
    const get = vi.spyOn(api.authorization, 'get').mockRejectedValue(new NetworkError('private'));
    await clock.advance();
    expect(get).toHaveBeenCalledOnce();
    expect(state.needsRefresh).toBe(false);
    expect(state.error).not.toContain('private');
    await clock.advance();
    expect(get).toHaveBeenCalledOnce();
    await clock.advance();
    expect(get).toHaveBeenCalledTimes(2);
    await clock.advance(600000);
    expect(clock.pending).toBe(0);
    expect(state.attempt).not.toBeNull();
    expect(state.error).toContain('paused');
    expect(state.monitoring).toBe(false);
    expect(new PersonalAccessViewState(() => state).status.action).toBe('check');
    await state.check();
    expect(start).toHaveBeenCalledOnce();
    state.dispose();
  });

  test('discovery failure retains authorization and requires facts before explicit retry', async (): Promise<void> => {
    const { state, api, clock, changed } = harness();
    await state.connect();
    await authorize(api);
    const discover = vi.spyOn(api.connections, 'discover').mockRejectedValueOnce(new NetworkError('secret'));
    await clock.advance();
    expect(state.selection.has_authorization).toBe(true);
    expect(state.error).toContain('Retry loading tools');
    expect(state.error).not.toContain('secret');
    expect(state.needsRefresh).toBe(true);
    await state.discover();
    expect(discover).toHaveBeenCalledOnce();
    discover.mockResolvedValue();
    const view = new PersonalAccessViewState(() => state);
    expect(view.menuActions.find((action) => action.id === 'retry-tools')?.disabled).toBe(false);
    await view.perform('retry-tools');
    expect(discover).toHaveBeenCalledTimes(2);
    expect(changed).toHaveBeenCalled();
    state.dispose();
  });

  test('focus coalesces a pending status read and owner replacement prevents discovery', async (): Promise<void> => {
    const { api, clock, browser } = harness();
    const dashboardApi = new InMemoryDashboardApi(catalogue);
    const dashboard = new DashboardState(dashboardApi, api, browser, clock);
    await dashboard.loadCatalogue();
    const state = dashboard.personalCards[0];
    await state.connect();
    const result = deferred<Attempt>();
    const get = vi.spyOn(api.authorization, 'get').mockReturnValue(result.promise);
    const discover = vi.spyOn(api.connections, 'discover');
    const checking = clock.advance();
    await dashboard.refreshOnFocus();
    expect(get).toHaveBeenCalledOnce();
    vi.spyOn(dashboardApi.catalogue, 'list').mockResolvedValue({ ...catalogue, identity_key: 'other-owner' });
    await dashboard.refreshOnFocus();
    result.resolve(completedAttempt);
    await checking;
    expect(discover).not.toHaveBeenCalled();
    expect(state.attempt).toBeNull();
    expect(clock.pending).toBe(0);
    dashboard.dispose();
  });

  test('catalogue failure after discovery offers read-only recovery without replay', async (): Promise<void> => {
    const { state, api, clock, changed } = harness();
    await state.connect();
    await authorize(api);
    const discover = vi.spyOn(api.connections, 'discover').mockResolvedValue();
    vi.mocked(changed).mockRejectedValueOnce(new Error('secret'));
    await clock.advance();
    expect(state.needsRefresh).toBe(true);
    expect(state.error).toContain('refresh the dashboard');
    expect(state.error).not.toContain('secret');
    await state.discover();
    expect(discover).toHaveBeenCalledOnce();
    await state.refresh();
    expect(discover).toHaveBeenCalledOnce();
    expect(state.needsRefresh).toBe(false);
    state.dispose();
  });

  test('a scheduled check consumed during a long safe refresh resumes afterward', async (): Promise<void> => {
    const { state, api, clock } = harness();
    await state.connect();
    const selectionRead = deferred<Selection>();
    vi.spyOn(api.connections, 'get').mockReturnValueOnce(selectionRead.promise);
    const get = vi.spyOn(api.authorization, 'get');
    const refreshing = state.refresh();
    await clock.advance();
    expect(get).not.toHaveBeenCalled();
    expect(clock.pending).toBe(1);
    selectionRead.resolve({ ...selection, has_authorization: false });
    await refreshing;
    await clock.advance();
    expect(get).toHaveBeenCalledOnce();
    expect(clock.pending).toBe(1);
    state.dispose();
  });

  test.each([403, 404])('permanent status %s stops monitoring and revalidates eligibility', async (status): Promise<void> => {
    const { state, api, clock, changed } = harness();
    await state.connect();
    const get = vi.spyOn(api.authorization, 'get').mockRejectedValue(new HttpError(status, 'private', {}));
    const read = vi.spyOn(api.connections, 'get');
    await clock.advance();
    expect(clock.pending).toBe(0);
    expect(read).toHaveBeenCalledOnce();
    expect(changed).toHaveBeenCalledOnce();
    expect(state.needsRefresh).toBe(true);
    await clock.advance(600000);
    expect(get).toHaveBeenCalledOnce();
    state.dispose();
  });

  test('completion owner read failure retains explicit tool loading intent even with old ready inventory', async (): Promise<void> => {
    const { state, api, clock } = harness();
    await state.connect();
    await authorize(api);
    vi.mocked(api.connections.get).mockRejectedValueOnce(new NetworkError('secret'));
    const discover = vi.spyOn(api.connections, 'discover').mockResolvedValue();
    await clock.advance();
    expect(state.attempt).toBeNull();
    expect(state.toolsNeedLoading).toBe(true);
    expect(state.needsRefresh).toBe(true);
    vi.mocked(api.connections.get).mockResolvedValue({ ...selection, runtime_available: true });
    expect(discover).not.toHaveBeenCalled();
    const view = new PersonalAccessViewState(() => state);
    expect(view.menuActions.find((action) => action.id === 'retry-tools')?.disabled).toBe(false);
    await view.perform('retry-tools');
    expect(discover).toHaveBeenCalledOnce();
    expect(state.toolsNeedLoading).toBe(false);
    state.dispose();
  });

  test('refresh is guarded throughout status checking and deferred completion discovery', async (): Promise<void> => {
    const { state, api, clock } = harness();
    await state.connect();
    await authorize(api);
    const discovery = deferred<void>();
    const discover = vi.spyOn(api.connections, 'discover').mockReturnValue(discovery.promise);
    const read = vi.mocked(api.connections.get);
    const checking = clock.advance();
    await vi.waitFor(() => expect(discover).toHaveBeenCalledOnce());
    const reads = read.mock.calls.length;
    const view = new PersonalAccessViewState(() => state);
    expect(view.menuActions.find((action) => action.id === 'refresh')?.disabled).toBe(true);
    await state.refresh();
    await state.retryLoadingTools();
    await state.discover();
    expect(read).toHaveBeenCalledTimes(reads);
    expect(state.loadingTools).toBe(true);
    expect(state.checking).toBe(true);
    expect(discover).toHaveBeenCalledOnce();
    discovery.resolve();
    await checking;
    expect(state.loadingTools).toBe(false);
    expect(state.checking).toBe(false);
    state.dispose();
  });

  test('a refresh requested during a status read cannot strand monitoring', async (): Promise<void> => {
    const { state, api, clock } = harness();
    await state.connect();
    const status = deferred<Attempt>();
    vi.spyOn(api.authorization, 'get').mockReturnValueOnce(status.promise);
    const read = vi.spyOn(api.connections, 'get');
    const checking = clock.advance();
    await state.refresh();
    expect(read).not.toHaveBeenCalled();
    status.resolve({ ...pendingAttempt });
    await checking;
    expect(state.monitoring).toBe(true);
    expect(clock.pending).toBe(1);
    await state.refresh();
    expect(clock.pending).toBe(1);
    state.dispose();
  });

  test.each(['same', 'changed', 'failed'] as const)('automatic completion waits for %s owner validation', async (outcome): Promise<void> => {
    const { api, clock, browser } = harness();
    const dashboardApi = new InMemoryDashboardApi(catalogue);
    const dashboard = new DashboardState(dashboardApi, api, browser, clock);
    await dashboard.loadCatalogue();
    const state = dashboard.personalCards[0];
    await state.connect();
    await authorize(api);
    const status = deferred<Attempt>();
    vi.mocked(api.authorization.get).mockReturnValueOnce(status.promise);
    const validation = deferred<typeof catalogue>();
    vi.spyOn(dashboardApi.catalogue, 'list').mockReturnValueOnce(validation.promise);
    const read = vi.mocked(api.connections.get);
    read.mockClear();
    const discover = vi.spyOn(api.connections, 'discover').mockResolvedValue();
    const checking = clock.advance();
    const focus = dashboard.refreshOnFocus();
    status.resolve(completedAttempt);
    for (let step = 0; step < 10; step++) await Promise.resolve();
    expect(read).not.toHaveBeenCalled();
    expect(discover).not.toHaveBeenCalled();
    expect(state.attempt).not.toBeNull();
    if (outcome === 'failed') validation.reject(new NetworkError('private'));
    else validation.resolve({ ...catalogue, identity_key: outcome === 'changed' ? 'other-owner' : catalogue.identity_key });
    await Promise.all([focus, checking]);
    if (outcome === 'same') expect(discover).toHaveBeenCalledOnce();
    else expect(discover).not.toHaveBeenCalled();
    if (outcome === 'failed') {
      expect(state.attempt).not.toBeNull();
      expect(state.checking).toBe(false);
      await dashboard.loadCatalogue();
      await clock.advance();
      expect(discover).toHaveBeenCalledOnce();
    }
    dashboard.dispose();
  });

  test('automatic completion follows the latest of successive identity validations', async (): Promise<void> => {
    const { api, clock, browser } = harness();
    const dashboardApi = new InMemoryDashboardApi(catalogue);
    const dashboard = new DashboardState(dashboardApi, api, browser, clock);
    await dashboard.loadCatalogue();
    const state = dashboard.personalCards[0];
    await state.connect();
    await authorize(api);
    const first = deferred<typeof catalogue>();
    const second = deferred<typeof catalogue>();
    vi.spyOn(dashboardApi.catalogue, 'list').mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
    const read = vi.mocked(api.connections.get);
    read.mockClear();
    const discover = vi.spyOn(api.connections, 'discover').mockResolvedValue();
    const validatingFirst = dashboard.loadCatalogue();
    const checking = clock.advance();
    for (let step = 0; step < 10; step++) await Promise.resolve();
    const validatingSecond = dashboard.loadCatalogue();
    first.resolve({ ...catalogue, identity_key: 'superseded-owner' });
    await validatingFirst;
    for (let step = 0; step < 10; step++) await Promise.resolve();
    expect(read).not.toHaveBeenCalled();
    expect(discover).not.toHaveBeenCalled();
    second.resolve(catalogue);
    await Promise.all([validatingSecond, checking]);
    expect(discover).toHaveBeenCalledOnce();
    dashboard.dispose();
  });

  test('automatic discovery rechecks identity after deferred owner details', async (): Promise<void> => {
    const { api, clock, browser } = harness();
    const dashboardApi = new InMemoryDashboardApi(catalogue);
    const dashboard = new DashboardState(dashboardApi, api, browser, clock);
    await dashboard.loadCatalogue();
    const state = dashboard.personalCards[0];
    await state.connect();
    await authorize(api);
    const details = deferred<Selection>();
    vi.mocked(api.connections.get).mockReturnValueOnce(details.promise);
    const discover = vi.spyOn(api.connections, 'discover').mockResolvedValue();
    const checking = clock.advance();
    await vi.waitFor(() => expect(state.readingDetails).toBe(true));
    const validation = deferred<typeof catalogue>();
    vi.spyOn(dashboardApi.catalogue, 'list').mockReturnValueOnce(validation.promise);
    const focus = dashboard.refreshOnFocus();
    details.resolve(selection);
    for (let step = 0; step < 10; step++) await Promise.resolve();
    expect(discover).not.toHaveBeenCalled();
    validation.resolve({ ...catalogue, identity_key: 'other-owner' });
    await Promise.all([focus, checking]);
    expect(discover).not.toHaveBeenCalled();
    dashboard.dispose();
  });

  test('uncertain enablement closes the reservation and never retries the mutation', async (): Promise<void> => {
    const { state, api, browser } = harness();
    const enable = vi.spyOn(api.connections, 'setEnablement').mockRejectedValue(new NetworkError('private'));
    const start = vi.spyOn(api.authorization, 'start');
    await state.connect();
    await state.connect();
    expect(enable).toHaveBeenCalledOnce();
    expect(start).not.toHaveBeenCalled();
    expect(browser.windows[0].closed).toBe(true);
    expect(state.needsRefresh).toBe(true);
    state.dispose();
  });
});
